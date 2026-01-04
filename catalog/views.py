from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from .forms import CourseForm, TopicForm, TopicLiteratureFormSet, TopicQuestionFormSet
from .models import Course, Topic, TopicLiterature, TopicQuestion


@login_required
@role_required("teacher", "dean", "admin")
def courses_list(request):
    if request.user.role == "admin":
        courses = Course.objects.all()
    else:
        courses = Course.objects.filter(owner=request.user)
    return render(request, "catalog/courses_list.html", {"courses": courses})


@login_required
@role_required("teacher", "dean", "admin")
def course_create(request):
    if request.method == "POST":
        form = CourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.owner = request.user
            course.save()
            return redirect("course_detail", pk=course.pk)
    else:
        form = CourseForm()
    return render(request, "catalog/course_form.html", {"form": form})


@login_required
@role_required("teacher", "dean", "admin")
def course_edit(request, pk):
    if request.user.role == "admin":
        course = get_object_or_404(Course, pk=pk)
    else:
        course = get_object_or_404(Course, pk=pk, owner=request.user)
    if request.method == "POST":
        form = CourseForm(request.POST, instance=course)
        if form.is_valid():
            course = form.save(commit=False)
            course.save()
            return redirect("course_detail", pk=course.pk)
    else:
        form = CourseForm(instance=course)
    return render(request, "catalog/course_form.html", {"form": form})


@login_required
def course_detail(request, pk):
    course = get_object_or_404(
        Course.objects.prefetch_related("topics__literature", "topics__questions"),
        pk=pk,
    )
    if course.owner != request.user and not course.is_shared and request.user.role not in [
        "admin",
        "dean",
        "umu",
        "program_leader",
    ]:
        raise PermissionDenied("Нет доступа к этому курсу.")
    topics = course.topics.order_by("order_index")
    return render(request, "catalog/course_detail.html", {"course": course, "topics": topics})


@login_required
@role_required("teacher", "dean", "admin")
def topic_create(request, course_pk):
    if request.user.role == "admin":
        course = get_object_or_404(Course, pk=course_pk)
    else:
        course = get_object_or_404(Course, pk=course_pk, owner=request.user)
    if request.method == "POST":
        form = TopicForm(request.POST)
        literature_formset = TopicLiteratureFormSet(request.POST, prefix="lit")
        question_formset = TopicQuestionFormSet(request.POST, prefix="q")
        if form.is_valid() and literature_formset.is_valid() and question_formset.is_valid():
            topic = form.save(commit=False)
            topic.course = course
            topic.save()

            literature_formset.instance = topic
            literature_formset.save()
            question_formset.instance = topic
            question_formset.save()

            return redirect("course_detail", pk=course.pk)
    else:
        form = TopicForm()
        literature_formset = TopicLiteratureFormSet(prefix="lit")
        question_formset = TopicQuestionFormSet(prefix="q")

    return render(
        request,
        "catalog/topic_form.html",
        {
            "course": course,
            "form": form,
            "literature_formset": literature_formset,
            "question_formset": question_formset,
        },
    )


@login_required
@role_required("teacher", "dean", "admin")
def topic_edit(request, course_pk, pk):
    if request.user.role == "admin":
        course = get_object_or_404(Course, pk=course_pk)
    else:
        course = get_object_or_404(Course, pk=course_pk, owner=request.user)
    topic = get_object_or_404(Topic, pk=pk, course=course)
    if request.method == "POST":
        form = TopicForm(request.POST, instance=topic)
        literature_formset = TopicLiteratureFormSet(request.POST, instance=topic, prefix="lit")
        question_formset = TopicQuestionFormSet(request.POST, instance=topic, prefix="q")
        if form.is_valid() and literature_formset.is_valid() and question_formset.is_valid():
            form.save()
            literature_formset.save()
            question_formset.save()
            return redirect("course_detail", pk=course.pk)
    else:
        form = TopicForm(instance=topic)
        literature_formset = TopicLiteratureFormSet(instance=topic, prefix="lit")
        question_formset = TopicQuestionFormSet(instance=topic, prefix="q")

    return render(
        request,
        "catalog/topic_form.html",
        {
            "course": course,
            "form": form,
            "literature_formset": literature_formset,
            "question_formset": question_formset,
        },
    )


@login_required
@role_required("teacher", "program_leader", "dean", "admin")
def shared_courses_list(request):
    courses = Course.objects.filter(is_shared=True).select_related("owner")
    return render(request, "catalog/shared_courses_list.html", {"courses": courses})


@login_required
@role_required("teacher", "dean", "admin")
@transaction.atomic
def course_fork(request, pk):
    source = get_object_or_404(Course, pk=pk, is_shared=True)

    new_course = Course.objects.create(
        owner=request.user,
        code=f"{source.code}_copy",
        title_ru=source.title_ru,
        title_kz=source.title_kz,
        title_en=source.title_en,
        description_ru=source.description_ru,
        description_kz=source.description_kz,
        description_en=source.description_en,
        available_languages=source.available_languages,
        is_shared=False,
    )

    for topic in source.topics.all().order_by("order_index"):
        new_topic = Topic.objects.create(
            course=new_course,
            order_index=topic.order_index,
            title_ru=topic.title_ru,
            title_kz=topic.title_kz,
            title_en=topic.title_en,
            description_ru=topic.description_ru,
            description_kz=topic.description_kz,
            description_en=topic.description_en,
            default_hours=topic.default_hours,
            week_type=topic.week_type,
            is_active=topic.is_active,
        )

        for lit in topic.literature.all():
            TopicLiterature.objects.create(
                topic=new_topic,
                title=lit.title,
                author=lit.author,
                year=lit.year,
                lit_type=lit.lit_type,
            )

        for q in topic.questions.all():
            TopicQuestion.objects.create(
                topic=new_topic,
                question_ru=q.question_ru,
                question_kz=q.question_kz,
                question_en=q.question_en,
            )

    return redirect("course_detail", pk=new_course.pk)
