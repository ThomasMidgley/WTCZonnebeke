from django.contrib.auth.models import Group, Permission

STOCK_GROUP = "Stockbeheerders"


def stock_group():
    group, created = Group.objects.get_or_create(name=STOCK_GROUP)
    if created or not group.permissions.filter(codename="access_admin").exists():
        permission = Permission.objects.get(content_type__app_label="wagtailadmin", codename="access_admin")
        group.permissions.add(permission)
    return group


def apply_role(user, role):
    """Zet de rechten van een gebruiker volgens de rol uit de instellingen Toegang."""
    user.is_active = True
    user.is_staff = role is not None
    user.is_superuser = role == "beheerder"
    user.save()
    group = stock_group()
    if role == "stockbeheerder":
        user.groups.add(group)
    else:
        user.groups.remove(group)
