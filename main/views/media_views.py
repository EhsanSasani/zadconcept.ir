from django.http import Http404


def private_story_source(request, filename=""):
    """Never expose raw story uploads, even behind a misconfigured proxy."""

    raise Http404
