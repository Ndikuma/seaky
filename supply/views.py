from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.contrib import messages
from .models import Cooperative, Member, MilkSupply, Payment, User,Medicine, MedicineRequest
from .forms import CooperativeForm, MemberForm, MilkSupplyForm, PaymentForm
from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Redirect based on user role
            if user.role == 'ADMIN':
                return redirect('admin_dashboard')
            elif user.role == 'MANAGER':
                return redirect('manager_dashboard')
            elif user.role == 'MEMBER':
                return redirect('member_dashboard')
            else:
                messages.error(request, "Invalid user role.")
                return redirect('login')
        else:
            messages.error(request, "Invalid username or password.")
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect('login')

@login_required
def admin_dashboard(request):
    if request.user.role != 'ADMIN':
        return HttpResponseForbidden("Access denied")
    context = {
        'cooperatives': Cooperative.objects.all(),
        'members': Member.objects.all(),
        'supplies': MilkSupply.objects.all(),
        'payments': Payment.objects.all(),
    }
    return render(request, 'admin_dashboard.html', context)

@login_required
def manager_dashboard(request):
    if request.user.role != 'MANAGER' or not request.user.member_profile:
        return HttpResponseForbidden("Access denied")
    member = request.user.member_profile
    if not member.cooperative:
        messages.error(request, "Manager is not assigned to a cooperative.")
        return redirect('member_dashboard')
    cooperative = request.user.member_profile.cooperative
    member = None
    if request.method == 'POST' and ' member_id' in request.POST:
        member_id = request.POST[' member_id'].strip()
        try:
            member = MemberProfile.objects.get( member_id= member_id, cooperative=cooperative)
        except MemberProfile.DoesNotExist:
            messages.error(request, "Membre non trouvé avec cet ID.")
    
    if request.user.role == 'MANAGER':
        supplies = MilkSupply.objects.filter(member__cooperative=cooperative)
        payments = Payment.objects.filter(member__cooperative=cooperative)
        total_milk_liters = supplies.aggregate(Sum('quantity_liters'))['quantity_liters__sum'] or 0
        total_payments =0

    else:  # MEMBER
        supplies = MilkSupply.objects.filter(member__user=request.user)
        payments = Payment.objects.filter(member__user=request.user)
        total_milk_liters = supplies.aggregate(Sum('quantity_liters'))['quantity_liters__sum'] or 0
        
        
    
    return render(request, 'manager_dashboard.html', {
        'cooperative': cooperative,
        'supplies': supplies,
        'payments': payments,
        'member': member,
        'total_milk_liters': total_milk_liters,
        'total_payments ':total_payments ,
    })
    
@login_required
def member_dashboard(request):
    if not request.user.member_profile:
        return HttpResponseForbidden("No member profile found")
    member = request.user.member_profile
    
    # Search and filter
    search_query = request.GET.get('search', '')
    supplies = member.milk_supplies.all()
    payments = member.payments.all()
    
    if search_query:
        supplies = supplies.filter(
            Q(supply_date__contains=search_query) |
            Q(quality_grade__icontains=search_query)
        )
        payments = payments.filter(
            Q(payment_date__contains=search_query) |
            Q(status__icontains=search_query) |
            Q(transaction_id__icontains=search_query)
        )
    
    # Pagination
    supplies_paginator = Paginator(supplies, 10)  # 10 supplies per page
    payments_paginator = Paginator(payments, 10)  # 10 payments per page
    page_number = request.GET.get('page')
    supplies = supplies_paginator.get_page(page_number)
    payments = payments_paginator.get_page(page_number)
    
    # Summary statistics
    total_liters = member.milk_supplies.aggregate(Sum('quantity_liters'))['quantity_liters__sum'] or 0
    total_payments = member.payments.filter(status='PAID').aggregate(Sum('amount'))['amount__sum'] or 0
    
    context = {
        'member': member,
        'supplies': supplies,
        'payments': payments,
        'total_liters': total_liters,
        'total_payments': total_payments,
    }
    return render(request, 'member_dashboard.html', context)

# Existing CRUD views (unchanged, included for completeness)
@login_required
def cooperative_list(request):
    if request.user.role != 'ADMIN':
        return HttpResponseForbidden("Access denied")
    cooperatives = Cooperative.objects.all()
    return render(request, 'cooperative_list.html', {'cooperatives': cooperatives})

@login_required
def cooperative_create(request):
    if request.user.role != 'ADMIN':
        return HttpResponseForbidden("Access denied")
    if request.method == 'POST':
        form = CooperativeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Cooperative created successfully.")
            return redirect('cooperative_list')
        else:
            messages.error(request, "Error creating cooperative.")
    else:
        form = CooperativeForm()
    return render(request, 'cooperative_form.html', {'form': form, 'title': 'Create Cooperative'})

@login_required
def cooperative_update(request, pk):
    if request.user.role != 'ADMIN':
        return HttpResponseForbidden("Access denied")
    cooperative = get_object_or_404(Cooperative, pk=pk)
    if request.method == 'POST':
        form = CooperativeForm(request.POST, instance=cooperative)
        if form.is_valid():
            form.save()
            messages.success(request, "Cooperative updated successfully.")
            return redirect('cooperative_list')
        else:
            messages.error(request, "Error updating cooperative.")
    else:
        form = CooperativeForm(instance=cooperative)
    return render(request, 'cooperative_form.html', {'form': form, 'title': 'Update Cooperative'})

@login_required
def cooperative_delete(request, pk):
    if request.user.role != 'ADMIN':
        return HttpResponseForbidden("Access denied")
    cooperative = get_object_or_404(Cooperative, pk=pk)
    if request.method == 'POST':
        cooperative.delete()
        messages.success(request, "Cooperative deleted successfully.")
        return redirect('cooperative_list')
    return render(request, 'cooperative_confirm_delete.html', {'cooperative': cooperative})

@login_required
def member_list(request):
    if request.user.role == 'ADMIN':
        members = Member.objects.all()
    elif request.user.role == 'MANAGER' and request.user.member_profile:
        member = request.user.member_profile
        members = Member.objects.filter(cooperative=member.cooperative)
    else:
        return HttpResponseForbidden("Access denied")
    return render(request, 'member_list.html', {'members': members})

@login_required
def member_create(request):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        return HttpResponseForbidden("Access denied")
    if request.method == 'POST':
        form = MemberForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            if User.objects.filter(username=username).exists():
                messages.error(request, "User with this username already exists.")
            else:
                user = User.objects.create_user(
                    username=username,
                    password=form.cleaned_data['password'],  # include password
                    email=form.cleaned_data.get('email', '')
                )
                member = form.save(commit=False)
                member.user = user
                if request.user.role == 'MANAGER':
                    member.cooperative = request.user.member_profile.cooperative
                member.save()
                messages.success(request, "Member created successfully.")
            return redirect('member_list')
        else:
            messages.error(request, "Error creating member.")
    else:
        form = MemberForm()


    return render(request, 'member_form.html', {'form': form, 'title': 'Create Member'})

@login_required
def member_update(request, pk):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        return HttpResponseForbidden("Access denied")
    member = get_object_or_404(Member, pk=pk)
    if request.user.role == 'MANAGER' and member.cooperative != request.user.member_profile.cooperative:
        return HttpResponseForbidden("Access denied")
    if request.method == 'POST':
        form = MemberForm(request.POST, instance=member)
        if form.is_valid():
            user = member.user
            user.username = form.cleaned_data['username']
            if form.cleaned_data['password']:
                user.set_password(form.cleaned_data['password'])
            user.role = form.cleaned_data['role']
            user.save()
            form.save()
            messages.success(request, "Member updated successfully.")
            return redirect('member_list')
        else:
            messages.error(request, "Error updating member.")
    else:
        form = MemberForm(instance=member, initial={'username': member.user.username, 'role': member.user.role})
        if request.user.role == 'MANAGER':
            form.fields['cooperative'].queryset = Cooperative.objects.filter(id=request.user.member_profile.cooperative.id)
    return render(request, 'member_form.html', {'form': form, 'title': 'Update Member'})

@login_required
def member_delete(request, pk):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        return HttpResponseForbidden("Access denied")
    member = get_object_or_404(Member, pk=pk)
    if request.user.role == 'MANAGER' and member.cooperative != request.user.member_profile.cooperative:
        return HttpResponseForbidden("Access denied")
    if request.method == 'POST':
        member.user.delete()
        member.delete()
        messages.success(request, "Member deleted successfully.")
        return redirect('member_list')
    return render(request, 'member_confirm_delete.html', {'member': member})

@login_required
def milk_supply_list(request):
    if request.user.role == 'ADMIN':
        supplies = MilkSupply.objects.all()
    elif request.user.role == 'MANAGER' and request.user.member_profile:
        member = request.user.member_profile
        supplies = MilkSupply.objects.filter(member__cooperative=member.cooperative)
    else:
        member = request.user.member_profile
        supplies = MilkSupply.objects.filter(member=member)
    return render(request, 'milk_supply_list.html', {'supplies': supplies})

@login_required
def milk_supply_create(request):
    if request.method == 'POST':
        form = MilkSupplyForm(request.POST, user=request.user)
        if form.is_valid():
            supply = form.save()
            messages.success(request, f"Milk supply of {supply.quantity_liters}L at ${supply.price_per_liter}/L recorded.")
            return redirect('milk_supply_list')
        else:
            messages.error(request, "Error recording milk supply.")
    else:
        form = MilkSupplyForm(user=request.user)
    return render(request, 'milk_supply_form.html', {'form': form, 'title': 'Add Milk Supply'})

@login_required
def milk_supply_update(request, pk):
    supply = get_object_or_404(MilkSupply, pk=pk)
    if request.user.role == 'MEMBER' and supply.member != request.user.member_profile:
        return HttpResponseForbidden("Access denied")
    if request.user.role == 'MANAGER' and supply.member.cooperative != request.user.member_profile.cooperative:
        return HttpResponseForbidden("Access denied")
    if request.method == 'POST':
        form = MilkSupplyForm(request.POST, instance=supply, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Milk supply updated successfully.")
            return redirect('milk_supply_list')
        else:
            messages.error(request, "Error updating milk supply.")
    else:
        form = MilkSupplyForm(instance=supply, user=request.user)
    return render(request, 'milk_supply_form.html', {'form': form, 'title': 'Update Milk Supply'})

@login_required
def milk_supply_delete(request, pk):
    supply = get_object_or_404(MilkSupply, pk=pk)
    if request.user.role == 'MEMBER' and supply.member != request.user.member_profile:
        return HttpResponseForbidden("Access denied")
    if request.user.role == 'MANAGER' and supply.member.cooperative != request.user.member_profile.cooperative:
        return HttpResponseForbidden("Access denied")
    if request.method == 'POST':
        supply.delete()
        messages.success(request, "Milk supply deleted successfully.")
        return redirect('milk_supply_list')
    return render(request, 'milk_supply_confirm_delete.html', {'supply': supply})

@login_required
def payment_list(request):
    if request.user.role == 'ADMIN':
        payments = Payment.objects.all()
    elif request.user.role == 'MANAGER' and request.user.member_profile:
        member = request.user.member_profile
        payments = Payment.objects.filter(member__cooperative=member.cooperative)
    else:
        member = request.user.member_profile
        payments = Payment.objects.filter(member=member)
    return render(request, 'payment_list.html', {'payments': payments})

@login_required
def payment_create(request):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        return HttpResponseForbidden("Access denied")
    if request.method == 'POST':
        form = PaymentForm(request.POST, user=request.user)
        if form.is_valid():
            payment = form.save(commit=False)
            supplies = form.cleaned_data['milk_supply_ids']
            payment.amount = sum(supply.total_value() for supply in supplies)
            payment.save()
            payment.milk_supply.set(supplies)
            if payment.status == 'PAID':
                payment.notify_member()
                messages.success(request, f"Payment of ${payment.amount:.2f} recorded and member notified.")
            else:
                messages.success(request, f"Payment of ${payment.amount:.2f} recorded.")
            return redirect('payment_list')
        else:
            messages.error(request, "Error processing payment.")
    else:
        form = PaymentForm(user=request.user)
    return render(request, 'payment_form.html', {'form': form, 'title': 'Process Payment'})

@login_required
def payment_update(request, pk):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        return HttpResponseForbidden("Access denied")
    payment = get_object_or_404(Payment, pk=pk)
    if request.user.role == 'MANAGER' and payment.member.cooperative != request.user.member_profile.cooperative:
        return HttpResponseForbidden("Access denied")
    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment, user=request.user)
        if form.is_valid():
            payment = form.save(commit=False)
            supplies = form.cleaned_data['milk_supply_ids']
            payment.amount = sum(supply.total_value() for supply in supplies)
            payment.save()
            payment.milk_supply.set(supplies)
            if payment.status == 'PAID' and not payment.notified:
                payment.notify_member()
            messages.success(request, "Payment updated successfully.")
            return redirect('payment_list')
        else:
            messages.error(request, "Error updating payment.")
    else:
        form = PaymentForm(instance=payment, user=request.user, initial={
            'milk_supply_ids': ','.join(str(s.id) for s in payment.milk_supply.all())
        })
    return render(request, 'payment_form.html', {'form': form, 'title': 'Update Payment'})

@login_required
def payment_delete(request, pk):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        return HttpResponseForbidden("Access denied")
    payment = get_object_or_404(Payment, pk=pk)
    if request.user.role == 'MANAGER' and payment.member.cooperative != request.user.member_profile.cooperative:
        return HttpResponseForbidden("Access denied")
    if request.method == 'POST':
        payment.delete()
        messages.success(request, "Payment deleted successfully.")
        return redirect('payment_list')
    return render(request, 'payment_confirm_delete.html', {'payment': payment})


def medicine_list(request):
    medicines = Medicine.objects.filter(stock_quantity__gt=0)
    return render(request, 'list_medicines.html', {'medicines': medicines})

@login_required
def request_medicine(request, medicine_id=None):
    if request.user.role != 'MEMBER':
        raise PermissionDenied("Only members can request medicine.")
    
    # Get all medicines with stock > 0 for potential dropdown (optional in template)
    medicines = Medicine.objects.filter(stock_quantity__gt=0)
    
    # Get the selected medicine if medicine_id is provided
    selected_medicine = None
    if medicine_id:
        selected_medicine = get_object_or_404(Medicine, id=medicine_id)
    
    if request.method == 'POST':
        quantity = request.POST.get('quantity')
        # Validate inputs
        try:
            quantity = int(quantity)
            if quantity <= 0:
                raise ValueError("Quantity must be positive.")
            medicine = get_object_or_404(Medicine, id=medicine_id)
            if quantity > medicine.stock_quantity:
                messages.error(request, f"Requested quantity exceeds available stock ({medicine.stock_quantity}).")
                return render(request, 'request_medicine.html', {
                    'medicines': medicines,
                    'selected_medicine': medicine
                })
            # Create the medicine request
            MedicineRequest.objects.create(
                member=request.user.member_profile,
                medicine=medicine,
                quantity=quantity
            )
            messages.success(request, f"Request for {medicine.name} submitted successfully.")
            return redirect('member_dashboard')
        
        except ValueError:
            messages.error(request, "Invalid quantity entered.")
            return render(request, 'request_medicine.html', {
                'medicines': medicines,
                'selected_medicine': medicine
            })

    # For GET requests, render the form
    return render(request, 'request_medicine.html', {
        'medicines': medicines,
        'selected_medicine': selected_medicine
    })

@login_required
def medicine_request_list(request):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        raise PermissionDenied("Only admins and managers can view requests.")
    requests = MedicineRequest.objects.all()
    if request.user.role == 'MANAGER':
        requests = requests.filter(member__cooperative=request.user.member_profile.cooperative)
    return render(request, 'medicine_request_list.html', {'requests': requests})

@login_required
def medicine_request_fulfill(request, pk):
    if request.user.role not in ['ADMIN', 'MANAGER']:
        raise PermissionDenied("Only admins and managers can fulfill requests.")
    medicine_request = get_object_or_404(MedicineRequest, pk=pk)
    if request.method == 'POST':
        quantity = int(request.POST.get('quantity'))
        try:
            message = medicine_request.fulfill(request.user, quantity)
            messages.success(request, message)
        except ValueError as e:
            messages.error(request, str(e))
        return redirect('medicine_request_list')
    return render(request, 'medicine_request_fulfill.html', {'request': medicine_request})


@login_required
def member_requests(request):
    if not hasattr(request.user, 'member_profile'):
        return render(request, 'member_requests.html', {'requests': []})
    requests = MedicineRequest.objects.filter(member=request.user.member_profile).order_by('-request_date')
    return render(request, 'member_requests.html', {'requests': requests})


def contact(request):
    medicines = Medicine.objects.filter(stock_quantity__gt=0)
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        # Send email (configure EMAIL_* settings)
        send_mail(
            f'Contact from {name}',
            f'Message from {name} ({email})',
            email,
            ['info@lifewayco.bi'],
            fail_silently=False,
        )
        messages.success(request, 'Your message has been sent!')
        return redirect('landing_page')
    return render(request, 'landing_page.html',{"medicines ":medicines })

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse

@csrf_exempt
def validate_member(request, member_id):
    cooperative = request.user.member_profile.cooperative
    try:
        member = Member.objects.get(member_id=member_id, cooperative=cooperative)
        print(member.id)
        return JsonResponse({
            'valid': True,
            'member': {
                'full_name': member.last_name or member.user.username,
                'email': member.user.email or 'Non défini'
            }
        })
    except Member.DoesNotExist:
        return JsonResponse({'valid': False}, status=404)