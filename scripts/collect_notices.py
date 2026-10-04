"""Bundle installed distributions' actual license/notice files, with provenance."""
import hashlib
import importlib.metadata as metadata
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DESTINATION=ROOT/'resources/third-party'

def collect():
    records=[]
    for distribution in metadata.distributions():
        name=distribution.metadata.get('Name','unknown')
        base=DESTINATION/'licenses'/re.sub(r'[^A-Za-z0-9_.-]','_',name+'-'+distribution.version)
        files=[]
        for entry in distribution.files or ():
            if any(token in entry.name.lower() for token in ('license','licence','copying','notice','copyright')) and entry.suffix.lower() not in ('.py','.pyc','.so','.dylib'):
                source=distribution.locate_file(entry)
                if source.is_file() and source.stat().st_size<2*1024*1024:
                    payload=source.read_bytes();target=base/(hashlib.sha256(str(entry).encode()).hexdigest()[:8]+'-'+entry.name)
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
                    files.append({'installed_path':str(entry),'bundled_path':str(target.relative_to(ROOT)), 'sha256':hashlib.sha256(payload).hexdigest()})
        records.append({'package':name,'version':distribution.version,'license':distribution.metadata.get('License-Expression') or distribution.metadata.get('License') or 'review required','files':files})
    DESTINATION.mkdir(parents=True,exist_ok=True)
    (DESTINATION/'manifest.json').write_text(json.dumps({'commercial_distribution_cleared':False,'dependencies':records},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': collect()
