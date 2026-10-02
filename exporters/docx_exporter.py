import os
import sys
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Inches

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def export(results, config):
    output_file = config.get("output_file", "Evidence_Report.docx")
    template_file = config.get("template_file", "template.docx")
    
    base_dir = get_base_dir()
    template_path = os.path.join(base_dir, template_file)
    output_path = os.path.join(base_dir, output_file)
    
    if not os.path.exists(template_path):
        print(f"Error: Template file '{template_file}' not found at {template_path}")
        return
        
    doc = DocxTemplate(template_path)
    
    # Prepare context for the template
    context = {
        'results': []
    }
    
    for res in results:
        res_context = dict(res)
        
        screenshot_path = res.get("screenshot_path")
        if screenshot_path and os.path.exists(screenshot_path):
            # docxtpl requires InlineImage to inject images into jinja tags
            res_context['screenshot'] = InlineImage(doc, screenshot_path, width=Inches(6.0))
        else:
            res_context['screenshot'] = None
            
        context['results'].append(res_context)
        
    doc.render(context)
    doc.save(output_path)
    print(f"Report successfully generated at: {os.path.abspath(output_path)}")
