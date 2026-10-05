from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.core.mail import send_mail
from django.core.validators import MinValueValidator
# Custom User Model
class User(AbstractUser):
    ROLE_CHOICES = [
        ('ADMIN', 'Admin'),
        ('MANAGER', 'Cooperative Manager'),
        ('MEMBER', 'Member'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='MEMBER')

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    def save(self, *args, **kwargs):
        # Accounts created with `createsuperuser` should land on the admin dashboard.
        if self._state.adding and self.is_superuser and self.role == 'MEMBER':
            self.role = 'ADMIN'
        super().save(*args, **kwargs)

# Cooperative Model
class Cooperative(models.Model):
    name = models.CharField(max_length=100, unique=True)
    location = models.CharField(max_length=200, blank=True)
    contact_info = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        indexes = [
            models.Index(fields=['name']),
        ]

# Member Model
class Member(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="member_profile")
    cooperative = models.ForeignKey(Cooperative, on_delete=models.SET_NULL, null=True, blank=True, related_name="members")
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    member_id = models.IntegerField(unique=True, editable=False)
    contact_number = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True, null=True)
    joined_date = models.DateField(default=timezone.now)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.member_id})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def save(self, *args, **kwargs):
        if not self.member_id:
            last = Member.objects.order_by('-member_id').first()
            self.member_id = (last.member_id + 1) if last else 100000
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['member_id']),
            models.Index(fields=['cooperative']),
        ]

# MilkSupply Model
class MilkSupply(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="milk_supplies")
    supply_date = models.DateField(default=timezone.now)
    quantity_liters = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)],
        help_text="Quantity of milk in liters"
    )
    quality_grade = models.CharField(max_length=10, choices=[
        ('A', 'Grade A'),
        ('B', 'Grade B'),
        ('C', 'Grade C')
    ], default='A')
    price_per_liter = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)],
        help_text="Price per liter in USD"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.member} - {self.quantity_liters}L at ${self.price_per_liter}/L on {self.supply_date}"

    def total_value(self):
        """Calculate total value of the supply."""
        return self.quantity_liters * self.price_per_liter

    class Meta:
        indexes = [
            models.Index(fields=['member', 'supply_date']),
            models.Index(fields=['supply_date']),
        ]

# Payment Model
class Payment(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="payments")
    milk_supply = models.ManyToManyField(MilkSupply, related_name="payments")
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)]
    )
    payment_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=[
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue')
    ], default='PENDING')
    transaction_id = models.CharField(max_length=50, blank=True, null=True)
    notified = models.BooleanField(default=False)

    def __str__(self):
        return f"Payment {self.id} for {self.member} - ${self.amount:.2f} ({self.status})"

    def calculate_amount(self):
        """Calculate total amount from linked milk supplies."""
        return sum(supply.total_value() for supply in self.milk_supply.all())

    def notify_member(self):
        """Notify member about payment with pricing details."""
        if self.notified or not self.member.email:
            return
        supplies = self.milk_supply.all()
        supply_details = "\n".join(
            f"- {supply.supply_date}: {supply.quantity_liters}L (Grade {supply.quality_grade}) "
            f"at ${supply.price_per_liter:.2f}/L = ${supply.total_value():.2f}"
            for supply in supplies
        )
        subject = f"Payment {self.status} - Seasky Milk"
        message = (
            f"Dear {self.member},\n\n"
            f"Your payment of ${self.amount:.2f} for milk supplied is {self.status.lower()}.\n\n"
            f"Details:\n{supply_details}\n\n"
            f"Transaction ID: {self.transaction_id or 'N/A'}\n"
            f"Payment Date: {self.payment_date}\n\n"
            f"Thank you,\nSeasky Team"
        )
        send_mail(
            subject=subject,
            message=message,
            from_email="seasky@example.com",
            recipient_list=[self.member.email],
            fail_silently=True,
        )
        self.notified = True
        self.save()

    class Meta:
        indexes = [
            models.Index(fields=['member', 'payment_date']),
            models.Index(fields=['status']),
        ]

from django.conf import settings
from django.utils.translation import gettext_lazy as _

class Medicine(models.Model):
    name = models.CharField(max_length=100, unique=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    image_url = models.ImageField(upload_to='medicines/', blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)],
        default=0.01
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    class Meta:
        ordering = ['name']
        verbose_name = "Medicine"
        verbose_name_plural = "Medicines"

    def __str__(self):
        return f"{self.name} (Stock: {self.stock_quantity})"

    def reduce_stock(self, quantity):
        if quantity > self.stock_quantity:
            raise ValueError(f"Insufficient stock for {self.name}.")
        self.stock_quantity -= quantity
        self.save()

class MedicineRequest(models.Model):
    STATUS_CHOICES = (
        ('PENDING', _('Pending')),
        ('FULFILLED', _('Fulfilled')),
    )

    member = models.ForeignKey('Member', on_delete=models.CASCADE, related_name='medicine_requests')
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='requests')
    quantity = models.PositiveIntegerField(help_text=_("Requested quantity"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    request_date = models.DateTimeField(auto_now_add=True)
    fulfilled_quantity = models.PositiveIntegerField(null=True, blank=True)
    fulfilled_date = models.DateTimeField(null=True, blank=True)
    fulfilled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-request_date']
        verbose_name = _("Medicine Request")
        verbose_name_plural = _("Medicine Requests")

    def __str__(self):
        return f"{self.member} - {self.medicine.name} ({self.quantity})"

    def fulfill(self, fulfilled_by, quantity):
        if self.status != 'PENDING':
            raise ValueError("Only pending requests can be fulfilled.")
        if quantity > self.quantity:
            raise ValueError("Fulfilled quantity exceeds requested quantity.")
        if quantity > self.medicine.stock_quantity:
            raise ValueError(f"Insufficient stock for {self.medicine.name}.")
        self.status = 'FULFILLED'
        self.fulfilled_quantity = quantity
        self.fulfilled_by = fulfilled_by
        self.fulfilled_date = timezone.now()
        self.medicine.reduce_stock(quantity)
        self.save()
        return f"Fulfilled {quantity} units of {self.medicine.name} for {self.member}."