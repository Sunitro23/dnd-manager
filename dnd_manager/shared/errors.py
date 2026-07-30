class ApplicationError(Exception):
    """Expected failure that can safely cross an application boundary."""


class InvalidRequest(ApplicationError):
    pass


class ResourceNotFound(ApplicationError):
    pass


class ConcurrentUpdate(ApplicationError):
    pass


class RepositoryUnavailable(ApplicationError):
    pass
