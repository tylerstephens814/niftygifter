import json

from django.http.response import Http404, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.urls.base import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Q, Count

from app import forms

from app.models import Chat, Notification, User, Event, Recipient, Idea


def home(request):
    if request.user.is_authenticated:
        events = Event.objects.exclude(members__id=request.user.id)
    else:
        events = Event.objects.all()
    context = {
        "events": events,
    }
    return render(request, "app/home.html", context)


def sign_out(request):
    logout(request)
    return redirect("home")


def sign_in(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = forms.SigninForm(request.POST if request.method == "POST" else None)

    if request.method == "POST":
        if form.is_valid():
            user = form.cleaned_data.get("user")
            if user:
                login(request, user)
                user.save()
                return redirect(request.GET.get("next") or "home")
    context = {
        "form": form,
    }
    return render(request, "registration/login.html", context)


def register(request):
    if request.method == "POST":
        form = forms.SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
    else:
        form = forms.SignupForm()
    context = {
        "form": form,
    }
    return render(request, "registration/register.html", context)


def event(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if request.POST.get("delete"):
        event.delete()
        return redirect("home")
    if request.POST.get("delete-contributor"):
        messages.success(request, "❌ Removed contributor.")
        event.members.remove(request.POST.get("delete-contributor"))
    recipients = event.recipients.order_by('id')
    if request.user.is_authenticated:
        recipients = event.recipients.annotate(
            notifications=Count(
                "ideas__notifications",
                filter=Q(
                    ideas__notifications__read=False,
                    ideas__notifications__user=request.user
                ),
            )
        )
    context = {
        "event": event,
        "recipients": recipients
    }
    return render(request, "app/event.html", context)


@login_required
def recipients_add_edit(request, event_id, recipient_id=None):
    event = get_object_or_404(Event, pk=event_id)
    recipient = None
    if recipient_id:
        recipient = get_object_or_404(Recipient, pk=recipient_id)
    if request.method == "POST":
        form = forms.NewRecipientForm(request.POST, instance=recipient, event=event)
        if form.is_valid():
            recipient = form.save(commit=False)
            recipient.event = event
            recipient.save()
            form.save_m2m()
            messages.success(request, "😎 Successfully saved recipient.")
            return redirect("event", event_id)
    else:
        form = forms.NewRecipientForm(instance=recipient, event=event)
    context = {
        "form": form,
    }
    return render(request, "app/recipient_add_edit.html", context)


@login_required
def recipient_ideas(request, event_id, recipient_id):
    recipient = get_object_or_404(Recipient, pk=recipient_id)
    ideas = recipient.ideas.select_related("creator").order_by("-id")
    ideas_ids = ideas.values_list('id', flat=True)
    Notification.objects.filter(content_type__model='idea', object_id__in=ideas_ids, user=request.user).update(read=True)

    context = {"recipient": recipient, "ideas": ideas}
    return render(request, "app/recipient.html", context)


# @login_required
# def event_recipients(request, event_id):
#     event = get_object_or_404(Event, pk=event_id)
#     if request.method == "POST":
#         form = forms.NewRecipientForm(request.POST, event=event)
#         if form.is_valid():
#             recipient = form.save(commit=False)
#             recipient.event = event
#             recipient.save()
#             form.save_m2m()
#             messages.success(request, "😎 Successfully added recipient.")
#     return redirect("event", event_id)


@login_required
def remove_event_recipient(request, event_id, recipient_id):
    get_object_or_404(Recipient, pk=recipient_id).delete()
    return redirect("event", event_id)


@login_required
def event_add_edit(request, pk=None):
    if pk:
        event = get_object_or_404(Event, pk=pk)
        if request.method == "POST":
            form = forms.EventForm(request.POST, instance=event)
            if form.is_valid():
                form.save()
                messages.success(request, "🗓 Event saved.")
                return redirect("event", event.id)
        else:
            form = forms.EventForm(instance=event)
    else:
        if request.method == "POST":
            form = forms.EventForm(request.POST)
            if form.is_valid:
                new_event = form.save(commit=False)
                new_event.organizer_id = request.user.id
                new_event.save()
                new_event.members.add(request.user)
                messages.success(request, "🗓 Event added.")
                return redirect("event", new_event.id)
        else:
            form = forms.EventForm()
    context = {"form": form}
    return render(request, "app/event_add_edit.html", context)


@login_required
def event_membership(request, pk):
    event = get_object_or_404(Event, pk=pk)
    if event.members.filter(id=request.user.id).exists():
        if request.user == event.organizer:
            messages.error(
                request, "You are the organizer, you cannot leave this event."
            )
            return redirect("event", pk)
        event.members.remove(request.user)
        return redirect("home")
    else:
        event.members.add(request.user)
        return redirect("event", pk)


def event_membership_async(request, event_id, user_id):
    user = get_object_or_404(User, pk=user_id)
    event = get_object_or_404(Event, pk=event_id)
    if event.members.filter(id=user_id).exists():
        if user == event.organizer:
            return HttpResponse(
                "You are the organizer, you cannot leave this event.", status=403
            )
        event.members.remove(user)
        return HttpResponse(status=200)
    else:
        event.members.add(user)
        return HttpResponse(status=200)


@login_required
def idea(request, event_id, recipient_id, pk):
    idea = get_object_or_404(Idea, pk=pk)
    context = {"idea": idea}
    return render(request, "app/idea.html", context)


@login_required
def idea_add_edit(request, event_id, recipient_id, pk=None):
    idea = None
    event = get_object_or_404(Event, pk=event_id)
    recipient = get_object_or_404(Recipient, pk=recipient_id)

    if pk:
        idea = get_object_or_404(Idea, pk=pk)
        if request.method == "POST":
            form = forms.IdeaForm(request.POST, instance=idea)
            if form.is_valid():
                form.save()
                messages.success(request, "💡 Idea saved.")
                return redirect("recipient_ideas", event_id, recipient_id)
        else:
            form = forms.IdeaForm(instance=idea)
    else:
        if request.method == "POST":
            form = forms.IdeaForm(request.POST)
            if form.is_valid:
                new_idea = form.save(commit=False)
                new_idea.creator = request.user
                new_idea.recipient_id = recipient_id
                new_idea.save()
                blocked_user_ids = recipient.blocked_users.values_list("id", flat=True)
                for user in event.members.exclude(id=request.user.id).exclude(id__in=blocked_user_ids):
                    Notification.objects.create(
                        user=user,
                        message="An idea was added",
                        content_object=new_idea,
                    )
                messages.success(request, "💡 Idea added.")
                return redirect("recipient_ideas", event_id, recipient_id)
        else:
            form = forms.IdeaForm()

    context = {
        "idea": idea,
        "form": form,
        "back": reverse("recipient_ideas", args=[event_id, recipient_id]),
    }
    return render(request, "app/idea_add_edit.html", context)


@login_required
def idea_delete(request, event_id, recipient_id, pk):
    idea = get_object_or_404(Idea, pk=pk)
    idea.delete()
    messages.success(request, "Success! Idea removed.")
    return redirect("recipient_ideas", event_id, recipient_id)


@login_required
def idea_like(request, event_id, recipient_id, pk):
    idea = get_object_or_404(Idea, pk=pk)
    if idea.likes.filter(id=request.user.id).exists():
        idea.likes.remove(request.user)
    else:
        idea.likes.add(request.user)
    return redirect("recipient_ideas", event_id, recipient_id)


def chat(request, pk):
    if request.method == "POST":
        body = json.loads(request.body)
        print(body)
        c = Chat.objects.create(
            user=request.user, group_id=pk, content=body.get("content")
        )
        return JsonResponse(c.serialize())
    if request.method == "GET":
        chats = Chat.objects.filter(group_id=pk).order_by("-id").select_related("user")
        return JsonResponse({"data": [c.serialize() for c in chats]})
    return Http404


# flag auto-add recipient when they join the group
# later add support for unsuspecting recipient
#
