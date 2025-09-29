from django import forms
from .models import Cooperative, Member, MilkSupply, Payment, User
from django.core.exceptions import ValidationError

COMMON_INPUT_CLASSES = 'mt-1 block w-full border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500'

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

    class Meta:
        model = Member
        fields = ['first_name', 'last_name', 'contact_number', 'email', 'joined_date']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., John'}),
            'last_name': forms.TextInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., Doe'}),
            'contact_number': forms.TextInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., +257...'}),
            'email': forms.EmailInput(attrs={'class': COMMON_INPUT_CLASSES, 'placeholder': 'e.g., john@example.com'}),
            'joined_date': forms.DateInput(attrs={'type': 'date', 'class': COMMON_INPUT_CLASSES}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and Member.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise ValidationError("This email is already used by another member.")
        return email


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
        self.fields['member'].queryset = Member.objects.none()

        if user and hasattr(user, 'member_profile'):
            member = user.member_profile

            if user.role == 'ADMIN':
                self.fields['member'].queryset = Member.objects.all()
            elif user.role == 'MANAGER' and member.cooperative:
                self.fields['member'].queryset = Member.objects.filter(cooperative=member.cooperative)
            elif user.role == 'MEMBER':
                self.fields['member'].queryset = Member.objects.filter(pk=member.pk)
                self.fields['member'].initial = member
                self.fields['member'].disabled = True
                self.fields['price_per_liter'].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        role = getattr(self.initial.get('user'), 'role', None)
        if role == 'MEMBER':
            grade = cleaned_data.get('quality_grade', 'A')
            price_map = {'A': 1.50, 'B': 1.20, 'C': 0.90}
            cleaned_data['price_per_liter'] = price_map.get(grade, 1.50)
        return cleaned_data

    def clean_quantity_liters(self):
        quantity = self.cleaned_data.get('quantity_liters', 0)
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        return quantity
    
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
        self.fields['member'].queryset = Member.objects.none()

        if user and hasattr(user, 'member_profile'):
            member = user.member_profile
            if user.role == 'ADMIN':
                self.fields['member'].queryset = Member.objects.all()
            elif user.role == 'MANAGER' and member.cooperative:
                self.fields['member'].queryset = Member.objects.filter(cooperative=member.cooperative)
            else:
                raise ValidationError("Only Admin or Manager can process payments.")

    def clean_milk_supply_ids(self):
        ids_str = self.cleaned_data.get('milk_supply_ids', '')
        try:
            ids = [int(i.strip()) for i in ids_str.split(',') if i.strip()]
            supplies = MilkSupply.objects.filter(id__in=ids, member=self.cleaned_data.get('member'))
            if not supplies.exists():
                raise ValidationError("No valid Milk Supply IDs found for this member.")
            return supplies
        except (ValueError, TypeError):
            raise ValidationError("Milk Supply IDs must be valid integers separated by commas.")
