from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Sum, Q
from django.views.decorators.http import require_GET

from .models import Cooperative, Member, MilkSupply, Payment, Medicine, MedicineRequest
from .forms import (
    CooperativeForm, MemberForm, MilkSupplyForm, PaymentForm, MedicineForm,
    get_member_profile, members_visible_to,
)


DASHBOARD_BY_ROLE = {
    'ADMIN': 'admin_dashboard',
    'MANAGER': 'manager_dashboard',
    'MEMBER': 'member_dashboard',
}


def role_required(*roles):
    """Restrict a view to logged-in users having one of the given roles."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                return HttpResponseForbidden("Access denied")
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def manager_cooperative(user):
    """The cooperative managed by a manager, or None."""
    profile = get_member_profile(user)
    return profile.cooperative if profile else None


def can_access_member(user, member):
    """Whether the user may view/edit records belonging to the given member."""
    if user.role == 'ADMIN':
        return True
    if user.role == 'MANAGER':
        cooperative = manager_cooperative(user)
        return cooperative is not None and member.cooperative_id == cooperative.pk
    return get_member_profile(user) == member


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect(DASHBOARD_BY_ROLE.get(request.user.role, 'landing_page'))
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.role not in DASHBOARD_BY_ROLE:
                messages.error(request, "Invalid user role.")
                return redirect('login')
            login(request, user)
            next_url = request.GET.get('next')
            if next_url and next_url.startswith('/') and not next_url.startswith('//'):
                return redirect(next_url)
            return redirect(DASHBOARD_BY_ROLE[user.role])
        messages.error(request, "Invalid username or password.")
    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('login')


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------

@role_required('ADMIN')
def admin_dashboard(request):
    context = {
        'cooperatives': Cooperative.objects.all(),
        'members': Member.objects.select_related('cooperative', 'user'),
        'supplies': MilkSupply.objects.select_related('member').order_by('-supply_date')[:20],
        'payments': Payment.objects.select_related('member').order_by('-payment_date')[:20],
        'total_milk_liters': MilkSupply.objects.aggregate(total=Sum('quantity_liters'))['total'] or 0,
        'total_paid': Payment.objects.filter(status='PAID').aggregate(total=Sum('amount'))['total'] or 0,
        'pending_requests': MedicineRequest.objects.filter(status='PENDING').count(),
    }
    return render(request, 'admin_dashboard.html', context)


@role_required('MANAGER')
def manager_dashboard(request):
    cooperative = manager_cooperative(request.user)
    if cooperative is None:
        messages.error(request, "Your account is not assigned to a cooperative. Contact an administrator.")
        return render(request, 'manager_dashboard.html', {'cooperative': None})

    supplies = (MilkSupply.objects.filter(member__cooperative=cooperative)
                .select_related('member__user').order_by('-supply_date'))
    payments = (Payment.objects.filter(member__cooperative=cooperative)
                .select_related('member__user').order_by('-payment_date'))
    total_milk_liters = supplies.aggregate(total=Sum('quantity_liters'))['total'] or 0
    total_payments = payments.filter(status='PAID').aggregate(total=Sum('amount'))['total'] or 0

    return render(request, 'manager_dashboard.html', {
        'cooperative': cooperative,
        'supplies': supplies,
        'payments': payments,
        'total_milk_liters': total_milk_liters,
        'total_payments': total_payments,
        'pending_requests': MedicineRequest.objects.filter(
            member__cooperative=cooperative, status='PENDING').count(),
    })


@login_required
def member_dashboard(request):
    member = get_member_profile(request.user)
    if member is None:
        if request.user.role in ('ADMIN', 'MANAGER'):
            return redirect(DASHBOARD_BY_ROLE[request.user.role])
        return HttpResponseForbidden("No member profile found")

    search_query = request.GET.get('search', '').strip()
    supplies = member.milk_supplies.order_by('-supply_date')
    payments = member.payments.order_by('-payment_date')

    if search_query:
        supplies = supplies.filter(
            Q(supply_date__icontains=search_query) |
            Q(quality_grade__iexact=search_query)
        )
        payments = payments.filter(
            Q(payment_date__icontains=search_query) |
            Q(status__icontains=search_query) |
            Q(transaction_id__icontains=search_query)
        )

    supplies = Paginator(supplies, 10).get_page(request.GET.get('supplies_page'))
    payments = Paginator(payments, 10).get_page(request.GET.get('payments_page'))

    context = {
        'member': member,
        'supplies': supplies,
        'payments': payments,
        'search_query': search_query,
        'total_liters': member.milk_supplies.aggregate(total=Sum('quantity_liters'))['total'] or 0,
        'total_payments': member.payments.filter(status='PAID').aggregate(total=Sum('amount'))['total'] or 0,
        'medicine_requests': member.medicine_requests.select_related('medicine')[:5],
    }
    return render(request, 'member_dashboard.html', context)


# ---------------------------------------------------------------------------
# Cooperatives (Admin only)
# ---------------------------------------------------------------------------

@role_required('ADMIN')
def cooperative_list(request):
    cooperatives = Cooperative.objects.all()
    return render(request, 'cooperative_list.html', {'cooperatives': cooperatives})


@role_required('ADMIN')
def cooperative_create(request):
    form = CooperativeForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Cooperative created successfully.")
            return redirect('cooperative_list')
        messages.error(request, "Error creating cooperative.")
    return render(request, 'cooperative_form.html', {'form': form, 'title': 'Create Cooperative'})


@role_required('ADMIN')
def cooperative_update(request, pk):
    cooperative = get_object_or_404(Cooperative, pk=pk)
    form = CooperativeForm(request.POST or None, instance=cooperative)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Cooperative updated successfully.")
            return redirect('cooperative_list')
        messages.error(request, "Error updating cooperative.")
    return render(request, 'cooperative_form.html', {'form': form, 'title': 'Update Cooperative'})


@role_required('ADMIN')
def cooperative_delete(request, pk):
    cooperative = get_object_or_404(Cooperative, pk=pk)
    if request.method == 'POST':
        cooperative.delete()
        messages.success(request, "Cooperative deleted successfully.")
        return redirect('cooperative_list')
    return render(request, 'cooperative_confirm_delete.html', {'cooperative': cooperative})


# ---------------------------------------------------------------------------
# Members (Admin, Manager within cooperative)
# ---------------------------------------------------------------------------

@role_required('ADMIN', 'MANAGER')
def member_list(request):
    members = members_visible_to(request.user).select_related('cooperative', 'user')
    search_query = request.GET.get('search', '').strip()
    if search_query:
        filters = (Q(first_name__icontains=search_query) |
                   Q(last_name__icontains=search_query) |
                   Q(user__username__icontains=search_query) |
                   Q(email__icontains=search_query))
        if search_query.isdigit():
            filters |= Q(member_id=int(search_query))
        members = members.filter(filters)
    members = Paginator(members.order_by('member_id'), 20).get_page(request.GET.get('page'))
    return render(request, 'member_list.html', {'members': members, 'search_query': search_query})


@role_required('ADMIN', 'MANAGER')
def member_create(request):
    if request.user.role == 'MANAGER' and manager_cooperative(request.user) is None:
        messages.error(request, "You must be assigned to a cooperative to add members.")
        return redirect('manager_dashboard')
    form = MemberForm(request.POST or None, user=request.user)
    if request.method == 'POST':
        if form.is_valid():
            with transaction.atomic():
                member = form.save()
            messages.success(request, f"Member {member.full_name} created (ID {member.member_id}).")
            return redirect('member_list')
        messages.error(request, "Error creating member.")
    return render(request, 'member_form.html', {'form': form, 'title': 'Create Member'})


@role_required('ADMIN', 'MANAGER')
def member_update(request, pk):
    member = get_object_or_404(Member, pk=pk)
    if not can_access_member(request.user, member):
        return HttpResponseForbidden("Access denied")
    form = MemberForm(request.POST or None, instance=member, user=request.user)
    if request.method == 'POST':
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, "Member updated successfully.")
            return redirect('member_list')
        messages.error(request, "Error updating member.")
    return render(request, 'member_form.html', {'form': form, 'title': 'Update Member'})


@role_required('ADMIN', 'MANAGER')
def member_delete(request, pk):
    member = get_object_or_404(Member, pk=pk)
    if not can_access_member(request.user, member):
        return HttpResponseForbidden("Access denied")
    if member.user_id == request.user.pk:
        messages.error(request, "You cannot delete your own account.")
        return redirect('member_list')
    if request.method == 'POST':
        # Deleting the user cascades to the member profile.
        member.user.delete()
        messages.success(request, "Member deleted successfully.")
        return redirect('member_list')
    return render(request, 'member_confirm_delete.html', {'member': member})


# ---------------------------------------------------------------------------
# Milk supplies
# ---------------------------------------------------------------------------

@login_required
def milk_supply_list(request):
    supplies = (MilkSupply.objects.filter(member__in=members_visible_to(request.user))
                .select_related('member').order_by('-supply_date', '-recorded_at'))
    return render(request, 'milk_supply_list.html', {'supplies': supplies})


@login_required
def milk_supply_create(request):
    data = request.POST or None
    # The manager dashboard modal identifies the member by their member number
    # (``member_id``) instead of the database primary key used by the form.
    if data is not None and 'member_id' in data and not data.get('member'):
        data = data.copy()
        member = members_visible_to(request.user).filter(
            member_id=data['member_id'].strip() if data['member_id'].strip().isdigit() else -1
        ).first()
        data['member'] = member.pk if member else ''

    form = MilkSupplyForm(data, user=request.user)
    if request.method == 'POST':
        if form.is_valid():
            supply = form.save()
            messages.success(
                request,
                f"Milk supply of {supply.quantity_liters}L for {supply.member} "
                f"at ${supply.price_per_liter}/L recorded."
            )
            if request.user.role == 'MANAGER' and 'member_id' in request.POST:
                return redirect('manager_dashboard')
            return redirect('milk_supply_list')
        if 'member_id' in request.POST and form.errors.get('member'):
            messages.error(request, "Member ID not found in your cooperative.")
        else:
            messages.error(request, "Error recording milk supply.")
    return render(request, 'milk_supply_form.html', {'form': form, 'title': 'Add Milk Supply'})


@login_required
def milk_supply_update(request, pk):
    supply = get_object_or_404(MilkSupply, pk=pk)
    if not can_access_member(request.user, supply.member):
        return HttpResponseForbidden("Access denied")
    form = MilkSupplyForm(request.POST or None, instance=supply, user=request.user)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Milk supply updated successfully.")
            return redirect('milk_supply_list')
        messages.error(request, "Error updating milk supply.")
    return render(request, 'milk_supply_form.html', {'form': form, 'title': 'Update Milk Supply'})


@login_required
def milk_supply_delete(request, pk):
    supply = get_object_or_404(MilkSupply, pk=pk)
    if not can_access_member(request.user, supply.member):
        return HttpResponseForbidden("Access denied")
    if request.method == 'POST':
        supply.delete()
        messages.success(request, "Milk supply deleted successfully.")
        return redirect('milk_supply_list')
    return render(request, 'milk_supply_confirm_delete.html', {'supply': supply})


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

@login_required
def payment_list(request):
    payments = (Payment.objects.filter(member__in=members_visible_to(request.user))
                .select_related('member').order_by('-payment_date'))
    return render(request, 'payment_list.html', {'payments': payments})


def _save_payment(request, form):
    with transaction.atomic():
        payment = form.save(commit=False)
        supplies = form.cleaned_data['milk_supplies']
        payment.amount = sum(supply.total_value() for supply in supplies)
        payment.save()
        payment.milk_supply.set(supplies)
    if payment.status == 'PAID' and not payment.notified:
        payment.notify_member()
    return payment


@role_required('ADMIN', 'MANAGER')
def payment_create(request):
    form = PaymentForm(request.POST or None, user=request.user)
    if request.method == 'POST':
        if form.is_valid():
            payment = _save_payment(request, form)
            messages.success(request, f"Payment of ${payment.amount:.2f} recorded.")
            return redirect('payment_list')
        messages.error(request, "Error processing payment.")
    return render(request, 'payment_form.html', {'form': form, 'title': 'Process Payment'})


@role_required('ADMIN', 'MANAGER')
def payment_update(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if not can_access_member(request.user, payment.member):
        return HttpResponseForbidden("Access denied")
    form = PaymentForm(request.POST or None, instance=payment, user=request.user, initial={
        'milk_supply_ids': ','.join(str(s.id) for s in payment.milk_supply.all())
    })
    if request.method == 'POST':
        if form.is_valid():
            _save_payment(request, form)
            messages.success(request, "Payment updated successfully.")
            return redirect('payment_list')
        messages.error(request, "Error updating payment.")
    return render(request, 'payment_form.html', {'form': form, 'title': 'Update Payment'})


@role_required('ADMIN', 'MANAGER')
def payment_delete(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if not can_access_member(request.user, payment.member):
        return HttpResponseForbidden("Access denied")
    if request.method == 'POST':
        payment.delete()
        messages.success(request, "Payment deleted successfully.")
        return redirect('payment_list')
    return render(request, 'payment_confirm_delete.html', {'payment': payment})


# ---------------------------------------------------------------------------
# Medicines
# ---------------------------------------------------------------------------

def medicine_list(request):
    medicines = Medicine.objects.filter(stock_quantity__gt=0)
    return render(request, 'list_medicines.html', {'medicines': medicines})


@role_required('ADMIN')
def add_medicine(request):
    form = MedicineForm(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        if form.is_valid():
            medicine = form.save()
            messages.success(request, f"{medicine.name} added to the catalogue.")
            return redirect('medicine_list')
        messages.error(request, "Error adding medicine.")
    return render(request, 'medicine_form.html', {'form': form, 'title': 'Add Medicine'})


@role_required('MEMBER')
def request_medicine(request, medicine_id):
    medicine = get_object_or_404(Medicine, id=medicine_id)
    member = get_member_profile(request.user)
    if member is None:
        return HttpResponseForbidden("No member profile found")

    if request.method == 'POST':
        try:
            quantity = int(request.POST.get('quantity', ''))
        except ValueError:
            quantity = 0
        if quantity <= 0:
            messages.error(request, "Invalid quantity entered.")
        elif quantity > medicine.stock_quantity:
            messages.error(request, f"Requested quantity exceeds available stock ({medicine.stock_quantity}).")
        else:
            MedicineRequest.objects.create(member=member, medicine=medicine, quantity=quantity)
            messages.success(request, f"Request for {medicine.name} submitted successfully.")
            return redirect('member_requests')

    return render(request, 'request_medicine.html', {'selected_medicine': medicine})


@login_required
def member_requests(request):
    member = get_member_profile(request.user)
    requests = (MedicineRequest.objects.filter(member=member).select_related('medicine')
                if member else MedicineRequest.objects.none())
    return render(request, 'member_requests.html', {'requests': requests})


@role_required('ADMIN', 'MANAGER')
def medicine_request_list(request):
    requests = MedicineRequest.objects.select_related('member', 'medicine', 'fulfilled_by')
    if request.user.role == 'MANAGER':
        requests = requests.filter(member__cooperative=manager_cooperative(request.user))
    status = request.GET.get('status')
    if status in ('PENDING', 'FULFILLED'):
        requests = requests.filter(status=status)
    return render(request, 'medicine_request_list.html', {'requests': requests, 'status': status})


@role_required('ADMIN', 'MANAGER')
def medicine_request_fulfill(request, pk):
    medicine_request = get_object_or_404(MedicineRequest, pk=pk)
    if not can_access_member(request.user, medicine_request.member):
        return HttpResponseForbidden("Access denied")
    if request.method == 'POST':
        try:
            quantity = int(request.POST.get('quantity', ''))
        except ValueError:
            quantity = 0
        if quantity <= 0:
            messages.error(request, "Invalid quantity entered.")
        else:
            try:
                with transaction.atomic():
                    message = medicine_request.fulfill(request.user, quantity)
                messages.success(request, message)
                return redirect('medicine_request_list')
            except ValueError as e:
                messages.error(request, str(e))
    return render(request, 'medicine_request_fulfill.html', {'medicine_request': medicine_request})


# ---------------------------------------------------------------------------
# Public pages & API
# ---------------------------------------------------------------------------

def contact(request):
    medicines = Medicine.objects.filter(stock_quantity__gt=0)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        message = request.POST.get('message', '').strip()
        if not (name and email and message):
            messages.error(request, 'Please fill in your name, email and message.')
        else:
            send_mail(
                f'Contact from {name}',
                f'Message from {name} ({email}):\n\n{message}',
                None,
                ['info@lifewayco.bi'],
                fail_silently=True,
            )
            messages.success(request, 'Your message has been sent!')
        return redirect('landing_page')
    return render(request, 'landing_page.html', {'medicines': medicines})


@require_GET
@role_required('ADMIN', 'MANAGER')
def validate_member(request, member_id):
    """Look up a member by member number within the caller's scope (used by the manager dashboard)."""
    member = None
    if member_id.isdigit():
        member = members_visible_to(request.user).select_related('user').filter(member_id=int(member_id)).first()
    if member is None:
        return JsonResponse({'valid': False}, status=404)
    return JsonResponse({
        'valid': True,
        'member': {
            'full_name': member.full_name or member.user.username,
            'email': member.email or member.user.email or 'Non défini',
        }
    })
