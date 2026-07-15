from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class ResilientManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """Hash available assets while tolerating externally preserved image assets.

    The delivered source archive does not contain ``main/static/main/img`` files.
    Missing paths therefore remain unhashed instead of making collectstatic or a
    template render fail. Once the image source tree is restored, those files are
    included in the manifest automatically.
    """

    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content=content, filename=filename)
        except ValueError as exc:
            if "could not be found" not in str(exc):
                raise
            return name
