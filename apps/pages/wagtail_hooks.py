from wagtail import hooks


@hooks.register("construct_main_menu")
def hide_builtin_forms_menu(request, menu_items):
    # Het ingebouwde menu "Formulieren" van Wagtail (berichten van het contactformulier) is overbodig:
    # die berichten gaan enkel per mail naar het bestuur. Onze eigen Formulieren blijven staan.
    menu_items[:] = [item for item in menu_items if item.name != "forms"]
