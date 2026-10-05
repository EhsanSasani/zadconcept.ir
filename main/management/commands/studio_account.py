"""Bootstrap ordinary florist and manager accounts without using Django Admin."""
from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from main.models import Florist


class Command(BaseCommand):
    help = "Create/link a Studio login; passwords are prompted and never passed in shell arguments."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--florist", help="Existing florist code to link to this account")
        parser.add_argument("--sales", action="store_true", help="Grant only the sales workspace permission")
        parser.add_argument("--manager", action="store_true", help="Grant Studio manager permissions (not Django Admin)")
        parser.add_argument("--reset-password", action="store_true", help="Prompt for a replacement password on an existing account")

    def handle(self, *args, **options):
        if not options["florist"] and not options["manager"] and not options["sales"]:
            raise CommandError("Choose --florist CODE, --sales and/or --manager.")
        User = get_user_model()
        username = User.normalize_username(options["username"].strip())
        try:
            User._meta.get_field("username").clean(username, User())
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        user = User.objects.filter(username__iexact=username).first()
        is_new = user is None
        if user is None:
            user = User(username=username)
        florist = None
        if options["florist"]:
            try:
                florist = Florist.objects.get(code__iexact=options["florist"].strip())
            except Florist.DoesNotExist as error:
                raise CommandError("Florist code does not exist. Create the florist profile first.") from error
            if not florist.is_active:
                raise CommandError("This florist profile is inactive.")
            if florist.user_id and florist.user_id != user.pk:
                raise CommandError("This florist already belongs to another account.")
            if user.pk and Florist.objects.filter(user=user).exclude(pk=florist.pk).exists():
                raise CommandError("This account is linked to a different florist.")
        change_password = is_new or options["reset_password"]
        if change_password:
            try:
                password = getpass("New password: ")
                repeated = getpass("Repeat password: ")
            except (EOFError, KeyboardInterrupt) as error:
                raise CommandError("Password prompt cancelled; no changes saved.") from error
            if password != repeated:
                raise CommandError("Passwords do not match; no changes saved.")
            try:
                validate_password(password, user)
            except ValidationError as error:
                raise CommandError(" ".join(error.messages)) from error
            user.set_password(password)
        with transaction.atomic():
            user.save()
            if florist:
                florist = Florist.objects.select_for_update().get(pk=florist.pk)
                if florist.user_id and florist.user_id != user.pk:
                    raise CommandError("This florist was linked by another request; no changes saved.")
                florist.user = user
                florist.save(update_fields=["user", "updated_at"])
            if options["sales"]:
                permission = Permission.objects.filter(content_type__app_label="main", codename="use_sales_workspace").first()
                if permission is None:
                    raise CommandError("Sales permission missing. Run migrate first.")
                group, _ = Group.objects.get_or_create(name="Studio sales")
                group.permissions.add(permission)
                user.groups.add(group)
            if options["manager"]:
                group, _ = Group.objects.get_or_create(name="Studio managers")
                codenames = {"view_studioproduct", "add_studioproduct", "change_studioproduct",
                             "view_florist", "add_florist", "change_florist", "manage_studio_accounts",
                             "change_studioingestionissue"}
                permissions = Permission.objects.filter(content_type__app_label="main", codename__in=codenames)
                if set(permissions.values_list("codename", flat=True)) != codenames:
                    raise CommandError("Studio permissions are missing. Run migrate first; no changes saved.")
                group.permissions.add(*permissions)
                user.groups.add(group)
        self.stdout.write(self.style.SUCCESS(
            f"Studio account {user.username} is ready. Login: /studio/login/"
            + (" (Existing password preserved.)" if not change_password else "")))
