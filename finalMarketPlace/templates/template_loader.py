"""
Template loader utility
"""
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Get templates directory
template_dir = os.path.dirname(os.path.abspath(__file__))

# Create Jinja2 environment
env = Environment(
    loader=FileSystemLoader(template_dir),
    autoescape=select_autoescape(['html', 'xml'])
)


def load_template(template_name: str, context: dict = None) -> str:
    """
    Load and render a template
    
    Args:
        template_name: Name of template file
        context: Dictionary of template variables
        
    Returns:
        Rendered HTML string
    """
    if context is None:
        context = {}
    
    template = env.get_template(template_name)
    return template.render(**context)