import zipfile
import xml.etree.ElementTree as ET
import json

EXCEL_PATH = '/Users/greg/Downloads/CREAL - Suivi Kanban TC.xlsx'
OUTPUT_JSON = '/Users/greg/.gemini/antigravity/scratch/creal-trinomes/data.json'
OUTPUT_JS = '/Users/greg/.gemini/antigravity/scratch/creal-trinomes/initialData.js'

ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def build_dataset():
    with zipfile.ZipFile(EXCEL_PATH) as z:
        shared_strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in tree.findall('ns:si', ns):
                t_elems = si.findall('.//ns:t', ns)
                shared_strings.append(''.join(t.text or '' for t in t_elems))
                
        wb_tree = ET.fromstring(z.read('xl/workbook.xml'))
        sheets_info = [s.attrib.get('name') for s in wb_tree.findall('.//ns:sheet', ns)]
        
        levels = ['P3', 'P4', 'P5', 'P6', 'S1', 'S2']
        all_modules = []
        known_cdcs = set()
        known_team = set()
        
        for idx, sname in enumerate(sheets_info):
            if sname in levels:
                sheet_xml = f'xl/worksheets/sheet{idx+1}.xml'
                stree = ET.fromstring(z.read(sheet_xml))
                rows = stree.findall('.//ns:row', ns)
                for r in rows:
                    r_num = int(r.attrib.get('r', 0))
                    if r_num < 3:
                        continue
                    cells = {}
                    for c in r.findall('ns:c', ns):
                        ref = c.attrib.get('r')
                        col = ''.join([ch for ch in ref if ch.isalpha()])
                        t = c.attrib.get('t')
                        v = c.find('ns:v', ns)
                        val = v.text if v is not None else None
                        if t == 's' and val is not None:
                            val = shared_strings[int(val)]
                        cells[col] = val
                    
                    cours = cells.get('A')
                    annee = cells.get('B')
                    module = cells.get('C')
                    coord = cells.get('D')
                    suppleant = cells.get('E')
                    cdc_nom = cells.get('F')
                    cdc_prenom = cells.get('G')
                    etape = cells.get('H')
                    commentaires = cells.get('K')
                    pct_str = cells.get('R')
                    
                    if cours and module:
                        cours = cours.strip()
                        if cours == 'Néelandais': cours = 'Néerlandais'
                        if cours == 'Scieces': cours = 'Sciences'
                            
                        if coord:
                            coord = coord.strip()
                            if coord in ['Grégory C.', 'Greg C']: coord = 'Greg C.'
                            if coord in ['Vincent ']: coord = 'Vincent'
                            if coord: known_team.add(coord)
                            
                        if suppleant:
                            suppleant = suppleant.strip()
                            if suppleant in ['Grégory C.', 'Greg C']: suppleant = 'Greg C.'
                            if suppleant == '?': suppleant = ''
                            if suppleant: known_team.add(suppleant)
                        
                        cdc_complet = ''
                        if cdc_prenom and cdc_nom:
                            cdc_complet = f'{cdc_prenom.strip()} {cdc_nom.strip()}'
                        elif cdc_nom:
                            cdc_complet = cdc_nom.strip()
                        elif cdc_prenom:
                            cdc_complet = cdc_prenom.strip()
                        
                        if cdc_complet:
                            known_cdcs.add(cdc_complet)
                        
                        pct_val = 0.0
                        try:
                            if pct_str: pct_val = round(float(pct_str) * 100, 1)
                        except:
                            pct_val = 0.0
                            
                        # Strict rule:
                        # - NO CdC:
                        #     * 100% or finalisé => 'Archivé'
                        #     * <100% => 'À venir'
                        # - WITH CdC:
                        #     * 100% & Terminé => 'Archivé'
                        #     * Otherwise => 'En cours' (requires trinôme)
                        if not cdc_complet:
                            if pct_val >= 99.0 or etape == 'Terminé' or (etape == 'Finalisation' and pct_val >= 90):
                                category = 'Archivé'
                            else:
                                category = 'À venir'
                        else:
                            if pct_val >= 100.0 and etape == 'Terminé':
                                category = 'Archivé'
                            else:
                                category = 'En cours'
                        
                        all_modules.append({
                            'id': f'{sname}_{cours}_{module}'.replace(' ', '_').replace('-', '_').replace("'", ''),
                            'level': sname,
                            'discipline': cours,
                            'module': module.strip(),
                            'coordinator': coord or '',
                            'backup': suppleant or '',
                            'cdc': cdc_complet or '',
                            'step': etape.strip() if etape else ('Terminé' if category == 'Archivé' else 'Non commencé'),
                            'progress': pct_val,
                            'category': category,
                            'comments': commentaires.strip() if commentaires else ''
                        })

        # S3 template (35 modules -> À venir)
        s3_disciplines = ['Français', 'Géographie', 'Histoire', 'Langues anciennes', 'Mathématiques', 'Sciences', 'Socio-éco']
        for d in s3_disciplines:
            for m in range(1, 6):
                all_modules.append({
                    'id': f'S3_{d}_Module_{m}'.replace(' ', '_').replace('-', '_').replace("'", ''),
                    'level': 'S3',
                    'discipline': d,
                    'module': f'Module {m}',
                    'coordinator': '',
                    'backup': '',
                    'cdc': '',
                    'step': 'Non commencé',
                    'progress': 0,
                    'category': 'À venir',
                    'comments': ''
                })

    team_list = [
        'Aurélie', 'Marco', 'Anne', 'Vincent', 'Lidwine', 'Hedwige', 
        'Nathalie', 'Greg L.', 'Greg C.', 'Maya', 'Jean-Luc', 'Marie-France', 
        'Mélanie', 'Mohamed'
    ]
    for t in sorted(list(known_team)):
        if t not in team_list:
            team_list.append(t)

    result = {
        'modules': all_modules,
        'team': team_list,
        'cdcs': sorted(list(known_cdcs)),
        'levels': ['P3', 'P4', 'P5', 'P6', 'S1', 'S2', 'S3'],
        'categories': ['En cours', 'À venir', 'Archivé'],
        'steps': ['Non commencé', 'Scénarisation', 'Section 1', 'Section 2', 'Section 3', 'Section 4', 'Section 5', 'Section 6', 'Section 7', 'Finalisation', 'Terminé']
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_JS, 'w', encoding='utf-8') as f:
        f.write('window.INITIAL_DATA = ' + json.dumps(result, ensure_ascii=False, indent=2) + ';\n')

    print(f"Data built: {len(all_modules)} modules. Cleaned.")

if __name__ == '__main__':
    build_dataset()
