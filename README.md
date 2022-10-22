# zaida

A comprehensive layout for your next social networking service. zaida strictly
follows REST principles (this repository does not contain a front-end
application).

## Purpose

This is just another social media application; however I'm trying to do more
than just a CRUD application. There are many pitfalls while designing social
media applications, especially when it comes to user relations and interactions.
To elaborate, here is an example from the auth module; a method that determines
if the message could be sent to a user:

````python
def can_send_message(self, to_user):
    if self == to_user:
        return False

    if not (to_user.is_accessible and self.is_accessible):
        return False

    if self.has_block_rel(to_user):
        # One of the users is blocking
        # another, so deny messages.
        return False

    if to_user.is_following(self):
        # The sender is followed by recipient, so messaging should
        # happen without intervention. A message request will be created
        # and accepted automatically, so in the future, (when this
        # relation breaks) participants can continue messaging each
        # other without having to send/accept new conversation requests.
        return True

    # If the recipient is not following the sender, we need
    # to look into conversation request relations.

    # In case this sender previously sent a conversation
    # request, and it was accepted by the recipient.
    recipient_accepted_request = ConversationRequest.objects.filter(
        date_accepted__isnull=False,
        sender=self,
        recipient=to_user,
    )

    if recipient_accepted_request.exists():
        return True

    try:
        # Check if this message is sent as a reply. To reply,
        # the user needs to accept the request first, so 'accept
        # date' should not be null to send this message.
        replying = ConversationRequest.objects.get(
            sender=to_user,
            recipient=self,
        )
        return replying.date_accepted is not None
    except ConversationRequest.DoesNotExist:
        # Not a reply either, this means it might be a new
        # conversation request, or new messages are added to
        # unaccepted request. Let's check if the user allows message
        # requests from strangers.
        return to_user.allows_all_messages
````

*Notice that remarkable amount of logic is already abstracted
away in other methods.*

And it's not just about logic; it is also important to figure out a good
database design and optimized queries while considering the overall
application design.

zaida (hopefully), will contain all the basic social-media related functionality
in order to bootstrap a new social media application; while being comprehensive
on
what it is doing.

## Feature rundown

* auth
    * CRU operations
    * Blocking operations
    * Following operations
      * Follow requests
      * Ability to mark profile 'private'
    * Profile pictures
      * Thumbnail generation
      * Image validation
          * Image scaling & compression on upload
          * Mime type validation
    * verification
        * Registration flow
          * No account generation before email validation
        * Password reset flow
        * Email change flow
* messaging
    * CRUD operations
    * One-to-one conversations & messaging
    * Message requests
    * Read receipts*
    * Ability to disable messages from strangers
    * Instant messaging with WebSocket
      *  Ticket-based authentication
* miscellaneous
  * Email service
  * Autogenerated API documentation
  * Unit-test & integration tests with high coverage
  * Ready to use development setup with Docker
  * technology stack
    * PostgreSQL as database
    * Redis as cache manager & broker
    * Celery as task queue
    * Python
      * Django web framework
      * django_rest_framework for REST API
      * channels for WebSocket support
