from django.shortcuts import get_object_or_404, redirect

from ..models import Category, Product


def product_detail(request, pk: int, slug: str):
    product = get_object_or_404(
        Product.objects.published()
        .select_related("category", "category__parent")
        .prefetch_related("tags", "gallery_images"),
        pk=pk,
    )

    return redirect(product.get_absolute_url(), permanent=True)

def flower_detail(request, pk: int, slug: str):
    flower = get_object_or_404(
        Product.objects.published()
        .filter(category__section=Category.Section.FLOWERS)
        .select_related("category")
        .prefetch_related("tags", "gallery_images"),
        pk=pk,
    )

    return redirect(flower.get_absolute_url(), permanent=True)

def flower_detail_redirect(request, pk: int):
    flower = get_object_or_404(
        Product.objects.published().filter(
            category__section=Category.Section.FLOWERS,
        ),
        pk=pk,
    )

    return redirect(flower.get_absolute_url(), permanent=True)
