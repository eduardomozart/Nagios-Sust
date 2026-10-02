import os
import sys
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Inches

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _diagnose_template_error(template_path):
    """Extracts and prints the tag hierarchy from the Word document to help debug template syntax errors."""
    try:
        import zipfile, re
        with zipfile.ZipFile(template_path) as z:
            xml = z.read('word/document.xml').decode('utf-8')
            text = re.sub(r'<[^>]+>', '', xml)
            tags = re.findall(r'\{[%\{].*?[%\}]\}', text)
            if not tags: return
            
            print("\n    --- Template Tags Found (In Order) ---")
            for i, tag in enumerate(tags):
                print(f"    Tag {i+1}: {tag}")
            print("    --------------------------------------")
            
            # Deep XML analysis to detect the "{%p mixed with other tags" issue
            paragraphs = re.findall(r'<w:p\b.*?</w:p>', xml, flags=re.DOTALL)
            conflict_found = False
            for p_idx, p_xml in enumerate(paragraphs):
                p_text = re.sub(r'<[^>]+>', '', p_xml)
                p_tags = re.findall(r'\{[%\{].*?[%\}]\}', p_text)
                if len(p_tags) > 1 and any(t.startswith('{%p') for t in p_tags):
                    print(f"    [Diagnosis] CRITICAL: Found a paragraph containing multiple tags including a {{%p tag!")
                    print(f"                Word Paragraph {p_idx+1} contains: {', '.join(p_tags)}")
                    conflict_found = True
                    break
                    
            if conflict_found:
                return

            # Validate tag pairs
            stack = []
            for i, tag in enumerate(tags):
                if not tag.startswith('{%'): continue
                
                content = tag.replace('{%', '').replace('%}', '').strip()
                parts = content.split()
                if not parts: continue
                
                cmd = parts[0]
                if cmd == 'p' and len(parts) > 1:
                    cmd = 'p ' + parts[1]
                    
                if cmd in ('if', 'for', 'p if', 'p for'):
                    stack.append((i+1, cmd, tag))
                elif cmd in ('endif', 'endfor', 'p endif', 'p endfor', 'else', 'p else'):
                    if cmd in ('else', 'p else'):
                        if not stack or not stack[-1][1].endswith('if'):
                            print(f"    [Diagnosis] Syntax Error on Tag {i+1}: Found '{tag}' without an opening 'if'.")
                            return
                        continue
                    
                    expected_opener = cmd.replace('end', '')
                    if not stack:
                        print(f"    [Diagnosis] Syntax Error on Tag {i+1}: Found '{tag}' but there are no open blocks.")
                        return
                    
                    last_open = stack.pop()
                    if last_open[1] != expected_opener:
                        print(f"    [Diagnosis] Syntax Error on Tag {i+1}: Found '{tag}' but expected closing for '{last_open[2]}' from Tag {last_open[0]}.")
                        return
                        
            if stack:
                unclosed = stack[-1]
                print(f"    [Diagnosis] Syntax Error: Reached end of document but '{unclosed[2]}' from Tag {unclosed[0]} was never closed.")
                
    except Exception:
        pass

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
        
        # Pre-calculate Summary Analytics
        summary = {
            "total": len(results),
            "counts": {
                "ok": 0,
                "warning": 0,
                "critical": 0,
                "offline": 0
            }
        }
        
        # Prepare context for the template
        context = {
            'results': [],
            'summary': summary
        }
        
        for res in results:
            res_context = dict(res)
            
            host = res.get("host", "Unknown")
            wan_stats = res.get("wan_status", {})
            
            # Grab all valid pings for this host from the standardized array
            pings = res.get("latencies", [])
            
            res_context["latency"] = ""
            res_context["status"] = "OFFLINE"
            
            if pings:
                worst_ping = max(pings) # Evaluate health based on their worst active link
                res_context["latency"] = worst_ping
                
                if worst_ping <= 50:
                    res_context["status"] = "OK"
                    summary["counts"]["ok"] += 1
                elif worst_ping <= 150:
                    res_context["status"] = "WARNING"
                    summary["counts"]["warning"] += 1
                else:
                    res_context["status"] = "CRITICAL"
                    summary["counts"]["critical"] += 1
            else:
                summary["counts"]["offline"] += 1
            
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
            
            _diagnose_template_error(template_path)
                
            print(f"\n    Skipping export for {lang} due to template error.\n")
            continue
