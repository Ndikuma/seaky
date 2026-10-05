from django.urls import path
from . import views


urlpatterns = [
    # Authentication routes
    path('login/', views.login_view, name='login'),
    path('', views.contact, name='landing_page'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard routes (role-specific)
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/manager/', views.manager_dashboard, name='manager_dashboard'),
    path('dashboard/member/', views.member_dashboard, name='member_dashboard'),

    # Cooperative CRUD routes (Admin only)
    path('cooperatives/', views.cooperative_list, name='cooperative_list'),
    path('cooperatives/create/', views.cooperative_create, name='cooperative_create'),
    path('cooperatives/<int:pk>/update/', views.cooperative_update, name='cooperative_update'),
    path('cooperatives/<int:pk>/delete/', views.cooperative_delete, name='cooperative_delete'),

    # Member CRUD routes (Admin, Manager within cooperative)
    path('members/', views.member_list, name='member_list'),
    path('members/create/', views.member_create, name='member_create'),
    path('members/<int:pk>/update/', views.member_update, name='member_update'),
    path('members/<int:pk>/delete/', views.member_delete, name='member_delete'),

    # Milk Supply CRUD routes (Admin, Manager within cooperative, Member for own supplies)
    path('milk-supplies/', views.milk_supply_list, name='milk_supply_list'),
    path('milk-supplies/create/', views.milk_supply_create, name='milk_supply_create'),
    path('milk-supplies/<int:pk>/update/', views.milk_supply_update, name='milk_supply_update'),
    path('milk-supplies/<int:pk>/delete/', views.milk_supply_delete, name='milk_supply_delete'),

    # Payment CRUD routes (Admin, Manager within cooperative)
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/create/', views.payment_create, name='payment_create'),
    path('payments/<int:pk>/update/', views.payment_update, name='payment_update'),
    path('payments/<int:pk>/delete/', views.payment_delete, name='payment_delete'),
    
    
    # Medicine routes
    path('medicine/', views.medicine_list, name='medicine_list'),
    path('medicine/add/', views.add_medicine, name='add_medicine'),
    path('request-medicine/<int:medicine_id>/', views.request_medicine, name='request_medicine'),
    path('medicine/my-requests/', views.member_requests, name='member_requests'),
    path('medicine/requests/', views.medicine_request_list, name='medicine_request_list'),
    path('medicine/requests/<int:pk>/fulfill/', views.medicine_request_fulfill, name='medicine_request_fulfill'),

    # API
    path('api/validate-member/<str:member_id>/', views.validate_member, name='validate_member'),

]
