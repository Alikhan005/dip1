from django.urls import path
from . import views

urlpatterns = [
    path("courses/", views.courses_list, name="courses_list"),
    path("courses/create/", views.course_create, name="course_create"),
    path("courses/<int:pk>/", views.course_detail, name="course_detail"),
    path("courses/<int:pk>/edit/", views.course_edit, name="course_edit"),
    path("courses/<int:course_pk>/topics/create/", views.topic_create, name="topic_create"),
    path("courses/<int:course_pk>/topics/<int:pk>/edit/", views.topic_edit, name="topic_edit"),
    path("courses/shared/", views.shared_courses_list, name="shared_courses_list"),
    path("courses/<int:pk>/fork/", views.course_fork, name="course_fork"),
]
