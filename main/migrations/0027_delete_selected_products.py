from django.db import migrations


PRODUCT_CODES_TO_DELETE = (
    "0669",
    "0480",
    "0473",
    "0474",
    "0468",
    "0463",
    "0455",
    "0796",
    "0783",
    "0441",
    "0437",
    "0438",
    "0435",
    "0433",
    "0426",
    "0421",
    "0413",
    "0773",
    "0511",
    "0662",
    "0674",
    "0506",
    "0507",
    "0508",
    "0492",
    "0502",
    "0776",
    "0568",
    "0521",
    "0514",
    "0475",
    "0451",
    "0446",
    "0445",
    "0430",
    "0424",
    "0423",
    "0714",
    "0709",
    "0710",
    "0703",
    "0702",
    "0698",
    "0694",
    "0695",
    "0646",
    "0620",
    "0652",
    "0648",
    "0625",
    "0628",
    "0609",
    "0606",
    "0598",
)


def delete_selected_products(apps, schema_editor):
    Product = apps.get_model("main", "Product")
    Product.objects.filter(product_code__in=PRODUCT_CODES_TO_DELETE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0026_workshop_types_and_gallery"),
    ]

    operations = [
        migrations.RunPython(
            delete_selected_products,
            reverse_code=None,
        ),
    ]
