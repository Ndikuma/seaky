from .forms import get_member_profile
from .models import MedicineRequest


def notifications(request):
    """Real counts for the notification bell in the navigation bar."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    requests = MedicineRequest.objects.filter(status='PENDING')
    if user.role == 'MANAGER':
        profile = get_member_profile(user)
        requests = requests.filter(member__cooperative=profile.cooperative if profile else None)
    elif user.role != 'ADMIN':
        profile = get_member_profile(user)
        requests = requests.filter(member=profile) if profile else requests.none()
    return {'pending_request_count': requests.count()}
