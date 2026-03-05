def sidebar_notifications(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {
            "sidebar_notifications": [],
            "sidebar_notifications_count": 0,
        }

    try:
        # Reuse existing role-based notification logic used on dashboard.
        from config.views import _build_dashboard_notifications, _count_unread_notifications
        from core.models import NotificationState

        state = NotificationState.objects.filter(user=request.user).first()
        last_seen_at = state.last_seen_at if state else None
        notifications = _build_dashboard_notifications(request.user, limit=None)
        unread_count = _count_unread_notifications(request.user, last_seen_at)
    except Exception:
        notifications = []
        unread_count = 0

    return {
        "sidebar_notifications": notifications,
        "sidebar_notifications_count": unread_count,
    }
