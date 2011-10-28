# -*- coding:utf-8 -*-
import re
import settings as tm_settings
from models import Message, Participant
from django.conf import settings
from django.contrib.sites.models import Site
from django.utils.encoding import force_unicode
from django.utils.text import wrap
from django.utils.translation import ugettext_lazy as _
from django.template import Context, loader
from django.template.loader import render_to_string, get_template
from django.template import Context
import HTMLParser
from lxml.html.clean import Cleaner
import datetime
if "notification" in settings.INSTALLED_APPS:
    from notification import models as notification
    
# favour django-mailer but fall back to django.core.mail
if tm_settings.THREADED_MESSAGES_USE_SENDGRID:
	import sendgrid_parse_api
	
if "mailer" in settings.INSTALLED_APPS:
    from mailer import send_mail
else:
    from django.core.mail import send_mail


def open_message_thread(recipients, subject, template,
                        sender, context={}, send=True):
    t = get_template(template)
    from forms import ComposeForm #temporary here to remove circular dependence
    compose_form = ComposeForm(data={
        "recipient": recipients,
        "subject": subject,
        "body": t.render(Context({}))
    })
    if compose_form.is_valid():
        compose_form.save(sender=sender, send=send)


def reply_to_thread(thread,sender, body):  
    # strip XSS and unwanted html
    h = HTMLParser.HTMLParser()
    cleaner = Cleaner(style=True, links=True, add_nofollow=True,
              page_structure=False, safe_attrs_only=True)
    body = cleaner.clean_html(h.unescape(body))

    new_message = Message.objects.create(body=body, sender=sender)
    new_message.parent_msg = thread.latest_msg
    thread.latest_msg = new_message
    thread.all_msgs.add(new_message)
    thread.replied = True
    thread.save()
    new_message.save()
    
    recipients = []
    for participant in thread.participants.all():
        participant.deleted_at = None
        participant.save()
        if sender != participant.user: # dont send emails to the sender!
            recipients.append(participant.user)
    
    sender_part = Participant.objects.get(thread=thread, user=sender)
    sender_part.replied_at = sender_part.read_at = datetime.datetime.now()
    sender_part.save()
    
    if notification:
        for r in recipients:
            if tm_settings.THREADED_MESSAGES_USE_SENDGRID:
                reply_email = sendgrid_parse_api.utils.create_reply_email(tm_settings.THREADED_MESSAGES_ID, r, thread)
                notification.send(recipients, "received_email", 
                                        {"thread": thread,
                                         "message": new_message}, sender=sender,
                                        from_email=reply_email.get_reply_email())
            else:
                notification.send(recipients, "received_email", 
                                    {"thread": thread,
                                     "message": new_message}, sender=sender)
        
    return (thread, new_message)
 