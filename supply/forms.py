from decimal import Decimal

from django import forms
from .models import Cooperative, Member, MilkSupply, Payment, User, Medicine
from django.core.exceptions import ValidationError

COMMON_INPUT_CLASSES = 'mt-1 block w-full border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500'

# Default price per liter (USD) applied when the price is not entered manually.
GRADE_PRICES = {
    'A': Decimal('1.50'),
    'B': Decimal('1.20'),
    'C': Decimal('0.90'),
}


def get_member_profile(user):
    """Return the user's Member profile, or None if it does not exist."""
    if user is None or not user.is_authenticated:
        return None
    try:
        return user.member_profile
    except Member.DoesNotExist:
        return None


def members_visible_to(user):
    """Members a user is allowed to act on, based on their role."""
    if user is None or not user.is_authenticated:
        return Member.objects.none()
    if user.role == 'ADMIN':
        return Member.objects.all()
    profile = get_member_profile(user)
    if profile is None:
        return Member.objects.none()
    if user.role == 'MANAGER' and profile.cooperative:
        return Member.objects.filter(cooperative=profile.cooperative)
    return Member.objects.filter(pk=profile.pk)


class CooperativeForm(forms.ModelForm):
    class Meta:
        model = Cooperative
        fields = ['name', 'location', 'contact_info']
        widgets = {
            'name': forms.TextInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., Seasky Cooperative'}),
            'location': forms.TextInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., 123 Dairy Road'}),
            'contact_info': forms.EmailInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., info@coop.bi'}),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise ValidationError("Cooperative name cannot be empty.")
        return name


class MemberForm(forms.ModelForm):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., johndoe'})
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'class': COMMON_INPUT_CLASSES}, render_value=False),
        help_text="Required for new members. Leave blank to keep the current password."
    )
    role = forms.ChoiceField(
        choices=User.ROLE_CHOICES,
        initial='MEMBER',
        widget=forms.Select(attrs={'class': COMMON_INPUT_CLASSES}),
    )

    class Meta:
        model = Member
        fields = ['first_name', 'last_name', 'cooperative', 'contact_number', 'email', 'joined_date']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., John'}),
            'last_name': forms.TextInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., Doe'}),
            'cooperative': forms.Select(attrs={'class': COMMON_INPUT_CLASSES}),
            'contact_number': forms.TextInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., +257...'}),
            'email': forms.EmailInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., john@example.com'}),
            'joined_date': forms.DateInput(attrs={'type': 'date', 'class': COMMON_INPUT_CLASSES}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if self.instance.pk:
            self.fields['username'].initial = self.instance.user.username
            self.fields['role'].initial = self.instance.user.role

        if user is not None and user.role == 'MANAGER':
            # Managers only manage plain members inside their own cooperative.
            del self.fields['cooperative']
            del self.fields['role']

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        existing = User.objects.filter(username=username)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.user_id)
        if existing.exists():
            raise ValidationError("A user with this username already exists.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not self.instance.pk and not password:
            raise ValidationError("A password is required for new members.")
        return password

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and Member.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise ValidationError("This email is already used by another member.")
        return email

    def save(self, commit=True):
        """Save the member together with its login account (always committed)."""
        member = super().save(commit=False)
        data = self.cleaned_data
        user = member.user if self.instance.pk else User()
        user.username = data['username']
        user.email = data.get('email') or ''
        user.first_name = data.get('first_name', '')
        user.last_name = data.get('last_name', '')
        if 'role' in self.fields:
            user.role = data['role']
        elif not user.role:
            user.role = 'MEMBER'
        if data.get('password'):
            user.set_password(data['password'])
        if self.user is not None and self.user.role == 'MANAGER':
            profile = get_member_profile(self.user)
            member.cooperative = profile.cooperative if profile else None
        user.save()
        member.user = user
        member.save()
        return member


class MilkSupplyForm(forms.ModelForm):
    class Meta:
        model = MilkSupply
        fields = ['member', 'supply_date', 'quantity_liters', 'quality_grade', 'price_per_liter']
        widgets = {
            'member': forms.Select(attrs={'class': COMMON_INPUT_CLASSES}),
            'supply_date': forms.DateInput(attrs={'type': 'date', 'class': COMMON_INPUT_CLASSES}),
            'quantity_liters': forms.NumberInput(attrs={'class': COMMON_INPUT_CLASSES, 'step': '0.01', 'min': '0.01'}),
            'quality_grade': forms.Select(attrs={'class': COMMON_INPUT_CLASSES}),
            'price_per_liter': forms.NumberInput(attrs={'class': COMMON_INPUT_CLASSES, 'step': '0.01', 'min': '0.01'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['member'].queryset = members_visible_to(user)
        self.fields['price_per_liter'].required = False
        self.fields['price_per_liter'].help_text = (
            "Leave blank to use the default price for the grade "
            "(A: $1.50, B: $1.20, C: $0.90)."
        )

        if user is not None and user.role == 'MEMBER':
            profile = get_member_profile(user)
            self.fields['member'].initial = profile
            self.fields['member'].disabled = True
            self.fields['price_per_liter'].disabled = True

    def clean_quantity_liters(self):
        quantity = self.cleaned_data.get('quantity_liters')
        if quantity is None or quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        return quantity

    def clean(self):
        cleaned_data = super().clean()
        grade = cleaned_data.get('quality_grade') or 'A'
        is_member = self.user is not None and self.user.role == 'MEMBER'
        if is_member or not cleaned_data.get('price_per_liter'):
            cleaned_data['price_per_liter'] = GRADE_PRICES.get(grade, GRADE_PRICES['A'])
        return cleaned_data


class PaymentForm(forms.ModelForm):
    milk_supply_ids = forms.CharField(
        widget=forms.TextInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., 1,2,3'}),
        help_text="Enter Milk Supply IDs (comma-separated)"
    )

    class Meta:
        model = Payment
        fields = ['member', 'payment_date', 'status', 'transaction_id']
        widgets = {
            'member': forms.Select(attrs={'class': COMMON_INPUT_CLASSES}),
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': COMMON_INPUT_CLASSES}),
            'status': forms.Select(attrs={'class': COMMON_INPUT_CLASSES}),
            'transaction_id': forms.TextInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., TX123'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and user.role in ('ADMIN', 'MANAGER'):
            self.fields['member'].queryset = members_visible_to(user)
        else:
            self.fields['member'].queryset = Member.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        member = cleaned_data.get('member')
        ids_str = cleaned_data.get('milk_supply_ids', '')
        if not member or not ids_str:
            return cleaned_data
        try:
            ids = [int(i.strip()) for i in ids_str.split(',') if i.strip()]
        except (ValueError, TypeError):
            self.add_error('milk_supply_ids', "Milk Supply IDs must be valid integers separated by commas.")
            return cleaned_data
        supplies = MilkSupply.objects.filter(id__in=ids, member=member)
        missing = set(ids) - set(supplies.values_list('id', flat=True))
        if not supplies.exists():
            self.add_error('milk_supply_ids', "No valid Milk Supply IDs found for this member.")
        elif missing:
            self.add_error(
                'milk_supply_ids',
                f"These IDs do not belong to this member: {', '.join(map(str, sorted(missing)))}."
            )
        else:
            cleaned_data['milk_supplies'] = supplies
        return cleaned_data


class MedicineForm(forms.ModelForm):
    class Meta:
        model = Medicine
        fields = ['name', 'description', 'price', 'stock_quantity', 'image_url']
        labels = {'image_url': 'Image'}
        widgets = {
            'name': forms.TextInput(attrs={'class': COMMON_INPUT_CLASSES}),
            'description': forms.Textarea(attrs={'class': COMMON_INPUT_CLASSES, 'rows': 3}),
            'price': forms.NumberInput(attrs={'class': COMMON_INPUT_CLASSES, 'step': '0.01', 'min': '0.01'}),
            'stock_quantity': forms.NumberInput(attrs={'class': COMMON_INPUT_CLASSES, 'min': '0'}),
        }
