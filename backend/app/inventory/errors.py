class InventoryError(ValueError):
    pass


class InventoryNotFound(InventoryError):
    pass


class InventoryConflict(InventoryError):
    pass


class InventoryValidation(InventoryError):
    pass
