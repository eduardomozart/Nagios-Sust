import os
import sys
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Inches

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def export(results, config):
    base_output_file = config.get("output_file", "Evidence_Report.docx")
    languages = config.get("language", ["en"])
    
    # Normalize to list to support both string and array formats in config
    if isinstance(languages, str):
        languages = [languages]
        
    for lang in languages:
        template_file = config.get("template_file", f"template_{lang}.docx")
        
        # If there are multiple languages, append the language code to the output file
        if len(languages) > 1:
            name, ext = os.path.splitext(base_output_file)
            output_file = f"{name}_{lang}{ext}"
        else:
            output_file = base_output_file
            
        base_dir = get_base_dir()
        template_path = os.path.join(base_dir, template_file)
        output_path = os.path.join(base_dir, output_file)
        
        if not os.path.exists(template_path):
            example_name = template_file.replace('.docx', '.example.docx')
            print(f"Error: Template file '{template_file}' not found.")
            print(f"Please copy or rename '{example_name}' to '{template_file}'.")
            continue
            
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
            
        try:
            doc.render(context)
            doc.save(output_path)
            print(f"Report ({lang}) successfully generated at: {os.path.abspath(output_path)}")
        except Exception as e:
            print(f"\n[!] Error rendering template '{template_file}' (Language: {lang})")
            print(f"    Details: {e}")
            
            # Extract and print tag hierarchy to help debug
            try:
                import zipfile, re
                with zipfile.ZipFile(template_path) as z:
                    xml = z.read('word/document.xml').decode('utf-8')
                    text = re.sub(r'<[^>]+>', '', xml)
                    tags = re.findall(r'\{[%\{].*?[%\}]\}', text)
                    if tags:
                        print("\n    --- Template Tags Found (In Order) ---")
                        for i, tag in enumerate(tags):
                            print(f"    Line {i+1}: {tag}")
                        print("    --------------------------------------")
                        print("    Tip: Check if every {% if %} has a matching {% endif %}.")
            except Exception as debug_e:
                pass
                
            print(f"\n    Skipping export for {lang} due to template error.\n")
            continue
