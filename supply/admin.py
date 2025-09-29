from django.contrib import admin
from .models import User, Cooperative, Member, MilkSupply, Payment,Medicine, MedicineRequest

admin.site.register(Medicine)
admin.site.register(MedicineRequest)
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'role')
    list_filter = ('role',)

@admin.register(Cooperative)
class CooperativeAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'contact_info')
    search_fields = ('name', 'contact_info')

@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'member_id', 'cooperative', 'email')
    list_filter = ('cooperative',)
    search_fields = ('first_name', 'last_name', 'member_id')

@admin.register(MilkSupply)
class MilkSupplyAdmin(admin.ModelAdmin):
    list_display = ('member', 'supply_date', 'quantity_liters', 'quality_grade', 'price_per_liter', 'total_value')
    list_filter = ('supply_date', 'quality_grade', 'member__cooperative')
    search_fields = ('member__member_id', 'member__first_name', 'member__last_name')

    def total_value(self, obj):
        return f"${obj.total_value()}"
    
    total_value.short_description = 'Total Value'

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('member', 'amount', 'payment_date', 'status', 'transaction_id', 'notified')
    list_filter = ('status', 'payment_date', 'member__cooperative')
    search_fields = ('member__member_id', 'transaction_id')
    actions = ['mark_as_paid']

    def mark_as_paid(self, request, queryset):
        for payment in queryset:
            payment.amount = payment.calculate_amount()
            payment.status = 'PAID'
            payment.save()
            payment.notify_member()
        self.message_user(request, "Payments marked as paid and members notified.")
    mark_as_paid.short_description = "Mark as paid and notify"