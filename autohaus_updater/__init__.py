# Set the value of '__version__'
try:
    # If setuptools_scm is installed (e.g. in a development environment),
    # then use it to determine the version dynamically.
    from setuptools_scm import get_version

    __version__ = get_version(root=".", relative_to=__file__)
except ImportError:
    # If setuptools_scm is not installed (e.g. in a release environment),
    # then use the version that is hard-coded in the file.
    try:
        from autohaus_updater._version import __version__  # noqa: F401
    except ModuleNotFoundError:
        raise RuntimeError(
            f"{__name__} is not correctly installed. Please install it with pip."
        )