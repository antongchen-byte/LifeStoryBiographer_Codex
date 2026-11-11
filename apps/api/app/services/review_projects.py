"""Capture immutable project records and materialize an isolated owner workspace."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
import tempfile
from sqlalchemy import select, DateTime
from .. import models as m, interview_models as i, cinema_models as c
from ..domain.errors import DomainError

MAIN = [m.Project, m.MediaAsset, m.InterviewerProfile, m.StyleSource, m.TranscriptTurn,
        m.StylePattern, m.StyleVersion, m.StyleJob, m.TranscriptArchive, m.ConversationMemoryTurn]
INTERVIEW = [i.InterviewConfig, i.InterviewChunk, i.InterviewSession, i.InterviewTurn,
             i.InterviewApproval, i.InterviewUploadRequest, i.InterviewMaterial,
             i.Screenplay, i.ScreenplaySection, i.ScreenplaySubsection, c.CinemaProduction, c.CinemaJob]


def records(db, model, field, values):
    return [{col.name:getattr(row,col.name) for col in model.__table__.columns}
            for row in db.scalars(select(model).where(getattr(model,field).in_(values)))]


def capture(main, db, project_id, screenplay_id=None, session_id=None, screenplay_revision=None):
    tables = {}
    def get(session, model, field, values):
        rows = records(session, model, field, values)
        tables[model.__tablename__] = rows
        return [r['id'] for r in rows]
    get(main,m.Project,'id',[project_id])
    get(main,m.MediaAsset,'project_id',[project_id])
    profiles=get(main,m.InterviewerProfile,'project_id',[project_id])
    sources=get(main,m.StyleSource,'profile_id',profiles)
    get(main,m.TranscriptTurn,'source_id',sources)
    for model in [m.StylePattern,m.StyleVersion,m.StyleJob]: get(main,model,'profile_id',profiles)
    archives=get(main,m.TranscriptArchive,'profile_id',profiles)
    get(main,m.ConversationMemoryTurn,'archive_id',archives)
    configs=get(db,i.InterviewConfig,'project_id',[project_id])
    get(db,i.InterviewChunk,'config_id',configs)
    screenplays=get(db,i.Screenplay,'project_id',[project_id])
    if screenplay_id:
        if screenplay_id not in screenplays:raise DomainError(404,'Selected screenplay is outside this project')
        tables['screenplays']=[s for s in tables['screenplays'] if s['id']==screenplay_id]
        screenplays=[screenplay_id]
        if screenplay_revision is not None and tables['screenplays'][0]['revision'] != screenplay_revision:
            raise DomainError(409,'The selected screenplay changed after preview. Reopen the share preview to confirm its latest saved revision')
    all_sessions=get(db,i.InterviewSession,'project_id',[project_id])
    if session_id and session_id not in all_sessions:raise DomainError(404,'Selected interview is outside this project')
    required={s['session_id'] for s in tables['screenplays'] if s.get('session_id')}
    if session_id:required.add(session_id)
    tables['interview_sessions']=[s for s in tables['interview_sessions'] if s['status']!='active' or s['id'] in required]
    if any(s['status']=='active' for s in tables['interview_sessions']):
        raise DomainError(409,'Save the selected interview or the selected screenplay’s source interview for review before sharing it. Other active interviews are excluded')
    sessions=[s['id'] for s in tables['interview_sessions']]
    for model in [i.InterviewTurn,i.InterviewApproval,i.InterviewUploadRequest,i.InterviewMaterial]: get(db,model,'session_id',sessions)
    sections=get(db,i.ScreenplaySection,'screenplay_id',screenplays)
    get(db,i.ScreenplaySubsection,'section_id',sections)
    productions=get(db,c.CinemaProduction,'screenplay_id',screenplays)
    current_revisions={s['id']:s['revision'] for s in tables['screenplays']}
    tables['cinema_productions']=[p for p in tables['cinema_productions'] if p['source_revision']==current_revisions[p['screenplay_id']]]
    productions=[p['id'] for p in tables['cinema_productions']]
    get(db,c.CinemaJob,'production_id',productions)
    for table in ['style_jobs','screenplays','cinema_jobs']:
        if any(r.get('state') in {'pending','dispatched','running','submitting','polling','stitching','processing','stopping'} for r in tables[table]):
            raise DomainError(409,'Wait for project generation jobs to finish before sharing a complete project version')
    if any(r.get('status') not in {'ready','failed'} for r in tables['media_assets']):
        raise DomainError(409,'Finish media uploads and processing before sharing a complete project version')
    from ..screenplay_schemas import source_hash
    from ..screenplay_routes import content_hash
    valid_drafts=[s['id'] for s in tables['screenplays'] if s['source'].get('draft_source_sha256')==source_hash(s['reviewed_markdown'],s['materials'])]
    valid_sections=[p['id'] for p in tables['screenplay_sections'] if any(s['id']==p['screenplay_id'] and s['source'].get('breakdown_hashes',{}).get(p['id'])==content_hash(p['content']) for s in tables['screenplays'])]
    return json.loads(json.dumps({'schema':1,'tables':tables,'valid_drafts':valid_drafts,'valid_sections':valid_sections},default=lambda v:v.value if hasattr(v,'value') else v.isoformat()))


def rewrite(value, mapping):
    if isinstance(value,dict):return {mapping.get(k,k):rewrite(v,mapping) for k,v in value.items()}
    if isinstance(value,list):return [rewrite(v,mapping) for v in value]
    if isinstance(value,str):
        if value in mapping:return mapping[value]
        # Embedded UIDs in Markdown must identify the cloned records too.
        for old,new in mapping.items():
            if len(old)==36:value=value.replace(old,new)
        return value
    return value


def copy_objects(snapshot, storage, prefix):
    keys=set()
    def visit(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in {'storage_key','thumbnail_key','proxy_key','audio_key','output_key','frame_key','key'} and isinstance(item,str) and item:
                    keys.add(item)
                else:visit(item)
        elif isinstance(value,list):
            for item in value:visit(item)
    visit(snapshot)
    mapping={}
    try:
        for key in sorted(keys):
            target=f'{prefix}/{m.new_id()}/{Path(key).name}'
            mapping[key]=target
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'object'
                storage.download(key,path)
                storage.put(target,path,(storage.head(key) or {}).get('ContentType','application/octet-stream'))
            mapping[key]=target
    except Exception:
        for key in mapping.values():storage.delete(key)
        raise DomainError(409,'A version material could not be copied. No editable project was created; retry or ask the editor to reshare the project') from None
    return rewrite(snapshot,mapping),list(mapping.values())


def materialize(main, db, review, user, storage):
    if not review.project_snapshot:
        raise DomainError(409,'This older version contains page text only. Ask the editor to share a new complete project version')
    if review.working_project_id and main.get(m.Project,review.working_project_id):
        return workspace(main,db,review.working_project_id,user.id)
    snapshot,keys=copy_objects(deepcopy(review.project_snapshot),storage,f'editable-copies/{user.id}/{m.new_id()}')
    tables=snapshot['tables']
    mapping={row['id']:m.new_id() for rows in tables.values() for row in rows}
    for row in tables['screenplays']:
        mapping.setdefault(row['interview_uid'],m.new_id())
    valid_drafts=set(rewrite(snapshot.get('valid_drafts',[]),mapping))
    valid_sections=set(rewrite(snapshot.get('valid_sections',[]),mapping))
    tables=rewrite(tables,mapping)
    project_id=tables['projects'][0]['id']
    inserted_interviews=False
    try:
        for session,models in [(main,MAIN),(db,INTERVIEW)]:
            for model in models:
                for data in tables[model.__tablename__]:
                    if 'owner_id' in data:data['owner_id']=user.id
                    for col in model.__table__.columns:
                        if isinstance(col.type,DateTime) and data.get(col.name):data[col.name]=datetime.fromisoformat(data[col.name])
                    if model is m.Project:
                        data['title']=('Editor-' + (data.get('title') or data['subject_name']))[:250]
                        data['created_at']=m.now()
                    if model is c.CinemaJob:
                        data['operation']=None
                    if model is i.Screenplay:
                        data['source'].pop('production_draft',None)
                        data['source'].pop('editor_id',None)
                        data['source']['from_editor_version']=review.id
                        # Identity remapping changes hashes; recalculate these after inserts.
                    session.add(model(**data))
                session.flush()
        main.add(m.ProjectMember(project_id=project_id,user_id=user.id,role='OWNER'))
        from ..screenplay_schemas import source_hash
        from ..screenplay_routes import content_hash
        for s in db.scalars(select(i.Screenplay).where(i.Screenplay.project_id==project_id)):
            source=dict(s.source)
            if s.id in valid_drafts:source['draft_source_sha256']=source_hash(s.reviewed_markdown,s.materials)
            existing=source.get('breakdown_hashes',{})
            source['breakdown_hashes']={p.id:content_hash(p.content) for p in db.scalars(select(i.ScreenplaySection).where(i.ScreenplaySection.screenplay_id==s.id)) if p.id in valid_sections}
            s.source=source
        db.flush()
        # Pin Cinema to the remapped screenplay content instead of old UID/hash metadata.
        from ..screenplay_routes import detail
        for production in db.scalars(select(c.CinemaProduction).where(c.CinemaProduction.screenplay_id.in_([s['id'] for s in tables['screenplays']]))):
            production.snapshot=detail(db,db.get(i.Screenplay,production.screenplay_id))
        # Rebuild the current Markdown export with new project/interview/screenplay UIDs.
        from ..screenplay_routes import markdown_export, digest
        from ..interview_routes import put_bytes
        for s in db.scalars(select(i.Screenplay).where(i.Screenplay.project_id==project_id)):
            if any(e['revision']==s.revision for e in s.exports):
                text=markdown_export(detail(db,s))
                key=f'editable-copies/{user.id}/{project_id}/{s.id}/screenplay.md'
                keys.append(key)
                put_bytes(storage,key,text.encode(),'text/markdown')
                s.exports=[{'revision':s.revision,'storage_key':key,'sha256':digest(text)}]
        db.commit();inserted_interviews=True
        review.working_project_id=project_id
        main.commit()
        return workspace(main,db,project_id,user.id)
    except Exception:
        db.rollback();main.rollback()
        if inserted_interviews:
            for model in reversed(INTERVIEW):
                ids=[row['id'] for row in tables[model.__tablename__]]
                db.query(model).filter(model.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
        for key in keys:storage.delete(key)
        raise


def workspace(main,db,project_id,actor_id):
    p=main.get(m.Project,project_id)
    config=db.scalar(select(i.InterviewConfig).where(i.InterviewConfig.project_id==project_id).order_by(i.InterviewConfig.created_at.desc()))
    screenplay=db.scalar(select(i.Screenplay).where(i.Screenplay.project_id==project_id).order_by(i.Screenplay.created_at.desc()))
    return {'id':p.id,'title':p.title,'actor_id':actor_id,'config_id':config.id if config else None,'screenplay_id':screenplay.id if screenplay else None}
