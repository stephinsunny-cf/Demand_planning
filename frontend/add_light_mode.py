import os
import re

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    replacements = {
        r'\bbg-slate-950\b': 'bg-slate-50 dark:bg-slate-950',
        r'\bbg-slate-900\b': 'bg-white dark:bg-slate-900',
        r'\bbg-slate-800\b': 'bg-slate-100 dark:bg-slate-800',
        r'\bbg-slate-800/50\b': 'bg-slate-100 dark:bg-slate-800/50',
        r'\bbg-slate-800/60\b': 'bg-slate-100 dark:bg-slate-800/60',
        r'\bbg-slate-800/80\b': 'bg-slate-100 dark:bg-slate-800/80',
        r'\bbg-slate-900/60\b': 'bg-white dark:bg-slate-900/60',
        r'\bbg-slate-900/40\b': 'bg-white dark:bg-slate-900/40',
        r'\bborder-slate-800\b': 'border-slate-200 dark:border-slate-800',
        r'\bborder-slate-700\b': 'border-slate-300 dark:border-slate-700',
        r'\btext-slate-400\b': 'text-slate-500 dark:text-slate-400',
        r'\btext-slate-300\b': 'text-slate-600 dark:text-slate-300',
        r'\btext-slate-200\b': 'text-slate-700 dark:text-slate-200',
        r'\btext-slate-100\b': 'text-slate-900 dark:text-slate-100',
        r'\btext-white\b': 'text-slate-900 dark:text-white',
        r'\bshadow-slate-900\b': 'shadow-slate-200 dark:shadow-slate-900',
    }
    
    new_content = content
    for pattern, repl in replacements.items():
        if repl not in new_content:
            new_content = re.sub(pattern, repl, new_content)
            
    # Fix the generic "CF" logo which has text-white but shouldn't be dark in light mode because its background is still dark.
    # We will manually correct specific places where we know it needs to remain white.
    new_content = new_content.replace('bg-[#011B4D] inline-flex items-center justify-center mb-0.5">\n            <span className="text-slate-900 dark:text-white font-extrabold text-[15px]', 'bg-[#011B4D] inline-flex items-center justify-center mb-0.5">\n            <span className="text-white font-extrabold text-[15px]')
    new_content = new_content.replace('bg-[#011B4D] inline-flex items-center justify-center mb-4 shadow-lg shadow-blue-500/10">\n              <span className="text-slate-900 dark:text-white font-extrabold text-2xl', 'bg-[#011B4D] inline-flex items-center justify-center mb-4 shadow-lg shadow-blue-500/10">\n              <span className="text-white font-extrabold text-2xl')

    # Also fix emerald/cyan buttons that had text-white
    new_content = new_content.replace('bg-emerald-500 hover:bg-emerald-400 text-slate-900 dark:text-white', 'bg-emerald-500 hover:bg-emerald-400 text-white')
    
    # Check if anything changed
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath}")

for root, dirs, files in os.walk('src'):
    for file in files:
        if file.endswith('.tsx') or file.endswith('.ts'):
            process_file(os.path.join(root, file))
