from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Template filter to get dictionary item by key"""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None