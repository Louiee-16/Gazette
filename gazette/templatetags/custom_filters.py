from django import template


register = template.Library()

@register.filter
def mask_name(value):
    return '*'* len(value)
