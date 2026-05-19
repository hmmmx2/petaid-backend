"""Domain layer for PetAid.

Contains the OO classes that map directly to the UML in the SRS:
- ``AppController`` (singleton coordinator)
- ``AuthManager`` (factory for Account subclasses)
- ``PaymentProcessor`` (adapter to external payment provider)
- ``MediaStorage`` (file validation + retrieval)
- ``Dashboard`` hierarchy (template method)
- ``EventBus`` (observer pattern)
- Domain ``Exceptions`` (InvalidCredentials / InvalidInput / AccountLocked)
"""
