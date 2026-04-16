from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary by key."""
    return dictionary.get(key)

@register.filter
def lookup(dictionary, key):
    """Alias for get_item filter."""
    return dictionary.get(key)
