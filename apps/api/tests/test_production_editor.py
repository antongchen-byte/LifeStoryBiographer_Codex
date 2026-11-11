import pytest
from sqlalchemy import select
from conftest import account
from test_screenplays import source  # noqa: F401
from test_cinema import production  # noqa: F401
from app.models import User, ProjectMember, ProductionRevision
from app.interview_models import InterviewConfig, Screenplay
from app.cinema_models import CinemaJob, CinemaProduction


@pytest.fixture
def editor_account(client, db):
    headers = account(client, "editor@example.com")
    user = db.scalar(select(User).where(User.email == "editor@example.com"))
    user.production_editor = True
    db.commit()
    return headers, user.id


def test_regular_accounts_keep_permissions_and_cannot_self_elevate(client, owner, project):
    assert client.get('/api/production/me', headers=owner).json()['production_editor'] is False
    assert client.get('/api/production/projects', headers=owner).status_code == 403
    forged = {**owner, 'X-Production-Project': project}
    assert client.get(f'/api/projects/{project}', headers=forged).status_code == 403
    assert client.patch(f'/api/projects/{project}', headers=owner, json={'title':'Still mine'}).status_code == 200
    assert client.get(f'/api/projects/{project}', headers=owner).json()['role'] == 'OWNER'
    response = client.post('/api/auth/register', json={'email':'forged@example.com','name':'Fake','password':'long-enough-password','production_editor':True})
    assert response.status_code == 422


def test_editor_selected_project_and_owner_identity(client, owner, project, editor_account, db, interview_db):
    editor, actor = editor_account
    second = client.post('/api/projects', headers=owner, json={'subject_name':'Other biography'}).json()['id']
    other = account(client, 'another-owner@example.com')
    third = client.post('/api/projects', headers=other, json={'subject_name':'Another owner'}).json()['id']
    assert {p['id'] for p in client.get('/api/production/projects',headers=editor).json()} == {project,second,third}
    scoped = {**editor, 'X-Production-Project':project}
    opened = client.post(f'/api/production/projects/{project}/open',headers=scoped)
    assert opened.status_code == 200, opened.text
    assert [p['id'] for p in client.get('/api/projects',headers=scoped).json()] == [project]
    assert client.get(f'/api/projects/{second}/media',headers=scoped).status_code == 404
    assert client.delete(f'/api/projects/{project}',headers=scoped).status_code == 403
    assert client.post(f'/api/projects/{project}/members',headers=scoped,json={'email':'editor@example.com','role':'EDITOR'}).status_code == 403
    response = client.post('/api/interviews/configs',headers=scoped,json={'project_id':project,'avatar':'flame','name':'Guide'})
    assert response.status_code == 201, response.text
    config = interview_db.get(InterviewConfig,response.json()['id'])
    owner_id = db.scalar(select(ProjectMember.user_id).where(ProjectMember.project_id==project,ProjectMember.role=='OWNER'))
    assert config.owner_id == owner_id != actor
    assert client.post('/api/interviews/configs',headers=scoped,json={'project_id':second,'avatar':'flame','name':'Wrong project'}).status_code == 404
    assert db.scalar(select(ProductionRevision).where(ProductionRevision.actor_id==actor))
    assert client.get(f'/api/projects/{project}',headers=editor).status_code == 404


def test_versioned_editor_drafts_and_owner_publication(client, owner, project, production, editor_account, db, interview_db):  # noqa: F811
    editor, actor = editor_account
    scoped = {**editor, 'X-Production-Project':project}
    original_id = production['screenplay_id']
    original = interview_db.get(Screenplay,original_id)
    original_revision = original.revision
    clip_ids=[]
    for index, unit in enumerate(production['units']):
        job=CinemaJob(production_id=production['id'],kind='clip',subsection_id=unit['id'],state='ready',request={'previous_id':None,'material_ids':[]},output_key=f'original/clip-{index}.mp4',frame_key=f'original/frame-{index}.png',sha256='a'*64,approved=True,previewed=True,duration=8)
        interview_db.add(job);interview_db.flush();clip_ids.append(job.id)
    interview_db.add(CinemaJob(production_id=production['id'],kind='stitch',state='ready',request={'clip_ids':clip_ids},output_key='original/final.mp4',sha256='b'*64))
    interview_db.commit()
    response=client.post(f'/api/production/projects/{project}/open',headers=scoped)
    assert response.status_code == 200,response.text
    draft_id=response.json()['screenplay_id']
    assert draft_id != original_id
    draft=interview_db.get(Screenplay,draft_id)
    assert draft.owner_id==original.owner_id and draft.source['editor_id']==actor
    assert client.get(f'/api/interviews/screenplays/{draft_id}',headers=owner).status_code == 404
    assert [s['id'] for s in client.get('/api/interviews/screenplays',headers=owner).json()] == [original_id]
    assert [s['id'] for s in client.get('/api/interviews/screenplays',headers=scoped).json()] == [draft_id]
    assert client.post(f'/api/interviews/screenplays/{original_id}/export',headers=scoped).status_code == 409
    loaded=client.post(f'/api/cinema/screenplays/{draft_id}',headers=scoped)
    assert loaded.status_code == 200,loaded.text
    copied=loaded.json()
    assert copied['units'][0]['clip']['download_url']
    assert copied['units'][0]['clip']['request']['actor_id']==actor
    assert copied['units'][0]['clip']['id'] != clip_ids[0]
    film=next(j for j in copied['renders'] if j['kind']=='stitch')
    assert client.get(f'/api/production/projects/{project}/releases',headers=owner).json()==[]
    assert client.post(f'/api/production/projects/{project}/publish',headers=scoped,json={'job_id':film['id']}).status_code==422
    published=client.post(f'/api/production/projects/{project}/publish',headers=scoped,json={'job_id':film['id'],'preview_confirmed':True})
    assert published.status_code==200,published.text
    assert len(client.get(f'/api/production/projects/{project}/releases',headers=owner).json())==1
    clip_share=client.post(f'/api/production/projects/{project}/publish-clips',headers=scoped,json={'production_id':copied['id']})
    assert clip_share.status_code==200,clip_share.text
    assert clip_share.json()['count']==len(copied['units'])
    assert client.post(f'/api/production/projects/{project}/publish-clips',headers=scoped,json={'production_id':copied['id']}).status_code==200
    released=client.get(f'/api/production/projects/{project}/releases',headers=owner).json()
    assert len(released)==len(copied['units'])+1
    assert sum(r['kind']=='clip' for r in released)==len(copied['units'])
    assert client.get(f'/api/cinema/{copied["id"]}',headers=owner).status_code==404
    version=client.get(f'/api/production/projects/{project}/versions',headers=scoped).json()[-1]['id']
    restored=client.post(f'/api/production/projects/{project}/versions/{version}/restore',headers=scoped,json={'screenplay_id':original_id})
    assert restored.status_code==200,restored.text
    assert restored.json()['screenplay_id'] not in {original_id,draft_id}
    interview_db.refresh(original)
    assert original.revision==original_revision
    assert client.get(f'/api/cinema/{production["id"]}',headers=owner).status_code==200


def test_owner_can_still_delete_empty_project_after_editor_visit(client, owner, project, editor_account):
    headers, _ = editor_account
    scoped = {**headers, "X-Production-Project":project}
    assert client.post(f"/api/production/projects/{project}/open",headers=scoped).status_code == 200
    assert client.delete(f"/api/projects/{project}",headers=owner).status_code == 204


def test_open_restores_owner_configuration_and_reference_selections(client, owner, project, editor_account):
    created = client.post('/api/interviews/configs', headers=owner, json={
        'project_id': project, 'avatar': 'female', 'name': 'Owner guide',
        'recommended_template_ids': ['life-story']})
    assert created.status_code == 201, created.text
    config_id = created.json()['id']
    scoped = {**editor_account[0], 'X-Production-Project': project}
    opened = client.post(f'/api/production/projects/{project}/open', headers=scoped)
    assert opened.status_code == 200, opened.text
    assert opened.json()['config_id'] == config_id
    route = f'/api/interviews/configs/{config_id}/markdown'
    original = client.get(route, headers=owner)
    restored = client.get(route, headers=scoped)
    assert restored.status_code == 200
    assert restored.json() == original.json()
    settings = restored.json()['configuration']
    assert settings['name'] == 'Owner guide'
    assert settings['avatar'] == 'female'
    assert settings['recommended'] == ['life-story']
    assert client.get(route, headers=editor_account[0]).status_code == 404


def test_generation_checkpoint_uses_bounded_audit_action(client, owner, project, editor_account, db):
    from app.models import AuditEvent
    scoped = {**editor_account[0], 'X-Production-Project': project}
    created = client.post('/api/interviews/screenplays', headers=scoped, json={
        'project_id': project, 'filename': 'source.md', 'markdown': '# Interview\n\nA family memory.'})
    assert created.status_code == 201, created.text
    screenplay = created.json()
    route = f'/api/interviews/screenplays/{screenplay["id"]}/generate'
    response = client.post(route, headers=scoped, json={
        'revision': screenplay['revision'], 'kind': 'draft', 'sections': 3, 'seconds': 8, 'consent': True})
    assert response.status_code == 200, response.text
    assert response.json()['state'] == 'pending'
    revision = db.scalar(select(ProductionRevision).where(ProductionRevision.action == 'POST ' + route))
    assert revision is not None
    audit = db.scalar(select(AuditEvent).where(AuditEvent.target_id == revision.id))
    assert audit.actor_id == editor_account[1]
    assert audit.project_id == project
    assert audit.action == 'production.checkpoint'
    assert len(audit.action) <= AuditEvent.__table__.c.action.type.length


def test_shared_page_versions_are_immutable_and_do_not_replace_owner_work(client, owner, project, editor_account, db):
    from uuid import uuid4
    from app.models import Project, ProductionReview
    editor_headers, actor_id = editor_account
    scoped = {**editor_headers, 'X-Production-Project': project}
    before = client.get(f'/api/projects/{project}', headers=owner).json()
    other = account(client, 'review-outsider@example.com')
    route = f'/api/production/projects/{project}/reviews'
    for module in ['biography', 'style', 'interview', 'screenplay', 'cinema']:
        body = {'module':module,'title':'Editor copy','content':'Changed description, only in this copy.', 'request_id':str(uuid4())}
        assert client.post(route, headers=owner, json=body).status_code == 403
        created = client.post(route, headers=scoped, json=body)
        assert created.status_code == 201, created.text
        assert created.json()['version_number'] == 1
        assert created.json()['editor_name']
        identifier = created.json()['id']
        assert client.post(route, headers=scoped, json=body).json()['id'] == identifier
        version_route = route + '/' + identifier
        assert client.get(version_route, headers=owner).json()['content'] == body['content']
        assert client.get(version_route, headers=other).status_code in {403,404}
        assert client.get(route, headers=other).status_code in {403,404}
        assert client.put(version_route, headers=scoped, json={'content':'Overwrite'}).status_code == 405
        row = db.get(ProductionReview, identifier)
        assert row.actor_id == actor_id
        assert row.owner_id != actor_id
    newer = client.post(route, headers=scoped, json={**body, 'request_id':str(uuid4()), 'content':'Another editor copy'})
    assert newer.status_code == 201
    assert newer.json()['version_number'] == 2
    assert client.get(version_route, headers=owner).json()['version_number'] == 1
    assert len(client.get(route, headers=owner).json()) == 6
    from app.models import OwnerNotification
    notifications = list(db.scalars(select(OwnerNotification)))
    assert len(notifications) == 6  # retries and denied requests do not send duplicates
    assert all(n.owner_id == row.owner_id for n in notifications)
    assert client.get(f'/api/projects/{project}', headers=owner).json() == before
    assert db.get(Project, project).description == before['description']
    second = client.post('/api/projects', headers=owner, json={'subject_name':'Another story'}).json()['id']
    assert client.get(f'/api/production/projects/{second}/reviews/{identifier}', headers=owner).status_code == 404
    assert client.post(f'/api/production/projects/{second}/reviews', headers=scoped, json=body).status_code == 403


def test_shared_version_opens_isolated_editable_project(client, owner, project, production, editor_account, db, interview_db, storage):
    from uuid import uuid4
    from app.models import Project, ProductionReview
    from app.interview_models import InterviewSession
    headers = {**editor_account[0], 'X-Production-Project':project}
    from app.models import MediaAsset, MediaStatus
    asset=MediaAsset(project_id=project,original_filename='photo.jpg',mime_type='image/jpeg',size_bytes=8,storage_key='original/photo.jpg',status=MediaStatus.ready)
    db.add(asset);db.commit()
    storage.objects['original/photo.jpg']=b'original'
    route = f'/api/production/projects/{project}/reviews'
    shared=client.post(route,headers=headers,json={'module':'cinema','title':'Complete version','content':'Page copy','request_id':str(uuid4())})
    assert shared.status_code==201,shared.text
    assert shared.json()['can_create_project']
    review_id=shared.json()['id']
    row=db.get(ProductionReview,review_id)
    assert row.project_snapshot['schema']==1
    storage.objects['original/photo.jpg']=b'changed later'
    opened=client.post(f'{route}/{review_id}/open-project',headers=owner)
    assert opened.status_code==200,opened.text
    copied=opened.json()
    assert copied['id'] != project
    copied_asset=db.scalar(select(MediaAsset).where(MediaAsset.project_id==copied['id']))
    assert copied_asset.storage_key != asset.storage_key
    assert storage.objects[copied_asset.storage_key]==b'original'
    assert copied['screenplay_id'] != production['screenplay_id']
    assert client.post(f'{route}/{review_id}/open-project',headers=owner).json()['id']==copied['id']
    scoped={**owner,'X-Workspace-Project':copied['id']}
    assert [p['id'] for p in client.get('/api/projects',headers=scoped).json()]==[copied['id']]
    assert client.get(f'/api/projects/{project}/media',headers=scoped).status_code==404
    assert client.get(f'/api/interviews/screenplays/{production["screenplay_id"]}',headers=scoped).status_code==404
    screenplays=client.get('/api/interviews/screenplays',headers=scoped).json()
    assert [s['id'] for s in screenplays]==[copied['screenplay_id']]
    assert screenplays[0]['cinema_ready']
    copied_screenplay=interview_db.get(Screenplay,copied['screenplay_id'])
    assert copied['screenplay_id'].encode() in storage.objects[copied_screenplay.exports[0]['storage_key']]
    cinema=client.post(f'/api/cinema/screenplays/{copied["screenplay_id"]}',headers=scoped)
    assert cinema.status_code==200,cinema.text
    assert cinema.json()['interview_uid'] != production['interview_uid']
    assert all(s['project_id']==copied['id'] for s in client.get('/api/interviews/configs',headers=scoped).json())
    assert client.patch(f'/api/projects/{copied["id"]}',headers=scoped,json={'description':'Only in copied project'}).status_code==200
    assert db.get(Project,project).description != 'Only in copied project'
    assert client.post(f'{route}/{review_id}/open-project',headers=editor_account[0]).status_code==403
    assert all(s.project_id==copied['id'] for s in interview_db.scalars(select(InterviewSession).where(InterviewSession.id.in_([s['id'] for s in client.get('/api/interviews/sessions',headers=scoped).json()]))))


def test_legacy_review_cannot_silently_clone_current_project(client, owner, project, editor_account, db):
    from uuid import uuid4
    from app.models import ProductionReview
    row=ProductionReview(project_id=project,owner_id=db.scalar(select(ProjectMember.user_id).where(ProjectMember.project_id==project)),actor_id=editor_account[1],request_id=str(uuid4()),module='biography',title='Old text',content='Text only')
    db.add(row);db.commit()
    response=client.post(f'/api/production/projects/{project}/reviews/{row.id}/open-project',headers=owner)
    assert response.status_code==409
    assert 'older version' in response.json()['detail']



def test_owner_can_preview_videos_in_shared_version_but_not_unapproved_takes(client, owner, project, editor_account, db):
    from copy import deepcopy
    from uuid import uuid4
    from app.models import ProductionReview
    from app.production_routes import snapshot_videos
    clip={'id':'clip','production_id':'production','kind':'clip','subsection_id':'sub','state':'ready','previewed':True,'approved':True,'output_key':'pinned/clip.mp4','request':{},'created_at':'2026-11-09T01:00:00Z'}
    film={'id':'film','production_id':'production','kind':'stitch','state':'ready','output_key':'pinned/film.mp4','request':{'clip_ids':['clip']},'created_at':'2026-11-09T02:00:00Z'}
    snapshot={'tables':{'cinema_productions':[{'id':'production','snapshot':{'title':'Shared film','sections':[{'position':1,'subsections':[{'id':'sub','position':1}]}]}}], 'cinema_jobs':[clip,film]}}
    row=ProductionReview(project_id=project,owner_id=db.scalar(select(ProjectMember.user_id).where(ProjectMember.project_id==project)),actor_id=editor_account[1],request_id=str(uuid4()),module='cinema',title='Shared film',content='Page text',project_snapshot=snapshot)
    db.add(row);db.commit()
    route=f'/api/production/projects/{project}/releases?review_id={row.id}'
    response=client.get(route,headers=owner)
    assert response.status_code==200
    assert {r['kind'] for r in response.json()}=={'clip','stitch'}
    assert all(r['review_id']==row.id for r in response.json())
    outsider=account(client,'video-outsider@example.com')
    assert client.get(route,headers=outsider).status_code==404
    replacement={**clip,'id':'alternate','approved':False,'created_at':'2026-11-09T03:00:00Z'}
    hidden=deepcopy(snapshot);hidden['tables']['cinema_jobs'].append(replacement)
    assert list(snapshot_videos(hidden))==[]


def test_share_pins_selected_screenplay_and_ignores_unrelated_active_interview(client, owner, project, production, editor_account, db, interview_db):
    from uuid import uuid4
    from app.models import ProductionReview
    from app.interview_models import InterviewSession
    original=interview_db.get(Screenplay,production['screenplay_id'])
    source_session=interview_db.get(InterviewSession,original.session_id)
    unrelated=InterviewSession(owner_id=original.owner_id,project_id=project,config_id=source_session.config_id,title='Another ongoing interview',model=original.model,status='active')
    interview_db.add(unrelated);interview_db.commit()
    scoped={**editor_account[0],'X-Production-Project':project}
    route=f'/api/production/projects/{project}/reviews'
    body={'module':'cinema','title':'Cinema shared version','content':'Current screenplay','request_id':str(uuid4()),'screenplay_id':original.id,'screenplay_revision':original.revision}
    response=client.post(route,headers=scoped,json=body)
    assert response.status_code==201,response.text
    assert response.json()['title'].startswith('Editor-')
    snapshot=db.get(ProductionReview,response.json()['id']).project_snapshot
    assert [s['id'] for s in snapshot['tables']['screenplays']]==[original.id]
    assert unrelated.id not in [s['id'] for s in snapshot['tables']['interview_sessions']]
    interview_db.refresh(unrelated)
    assert unrelated.status=='active'
    changed=client.post(route,headers=scoped,json={**body,'request_id':str(uuid4()),'screenplay_revision':original.revision+1})
    assert changed.status_code==409
    assert 'changed after preview' in changed.json()['detail']
    selected_active=client.post(route,headers=scoped,json={**body,'request_id':str(uuid4()),'session_id':unrelated.id})
    assert selected_active.status_code==409
    assert 'selected interview' in selected_active.json()['detail']


def test_cloud_film_studios_are_editor_only_without_blocking_shared_materials(client, owner, project, editor_account, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings,'film_studios_editor_only',True)
    assert client.get('/api/interviews/screenplays',headers=owner).status_code==403
    assert client.post('/api/cinema/screenplays/unknown',headers=owner).status_code==403
    assert client.get('/api/interviews/configs',headers=owner).status_code==200
    assert client.get(f'/api/production/projects/{project}/reviews',headers=owner).status_code==200
    assert client.get(f'/api/production/projects/{project}/releases',headers=owner).status_code==200
    assert client.get('/api/production/projects',headers=editor_account[0]).status_code==200
    assert client.get('/api/interviews/screenplays',headers=editor_account[0]).status_code==200
    monkeypatch.setattr(settings,'film_studios_editor_only',False)
    assert client.get('/api/interviews/screenplays',headers=owner).status_code==200


def test_cinema_editor_can_choose_project_photos_without_screenplay_selection(client, owner, project, production, editor_account, db, interview_db, storage):
    from app.models import MediaAsset, MediaStatus
    from app.cinema_models import CinemaJob
    from test_cinema import generate
    headers, _ = editor_account
    scoped = {**headers, 'X-Production-Project': project}
    opened = client.post(f'/api/production/projects/{project}/open', headers=scoped).json()
    loaded = client.post(f"/api/cinema/screenplays/{opened['screenplay_id']}", headers=scoped).json()
    other = client.post('/api/projects', headers=owner, json={'subject_name':'Separate biography'}).json()['id']
    def photo(pid, name, status=MediaStatus.ready):
        a = MediaAsset(project_id=pid, original_filename=name, mime_type='image/png',
            size_bytes=5, storage_key=name, status=status)
        db.add(a); db.flush()
        storage.objects[name] = b'photo'
        return a
    available = photo(project, 'new-photo.png')
    foreign = photo(other, 'foreign-photo.png')
    pending = photo(project, 'pending-photo.png', MediaStatus.uploading)
    db.commit()
    refreshed = client.get(f"/api/cinema/{loaded['id']}", headers=scoped).json()
    ids = {m['id'] for m in refreshed['materials']}
    assert refreshed['all_project_photos']
    assert available.id in ids and foreign.id not in ids and pending.id not in ids
    assert available.id not in refreshed['units'][0]['content']['material_ids']
    assert generate(client, scoped, refreshed, 0, material_ids=[foreign.id]).status_code == 422
    response = generate(client, scoped, refreshed, 0, material_ids=[available.id])
    assert response.status_code == 202, response.text
    job = interview_db.get(CinemaJob, response.json()['units'][0]['clip']['id'])
    assert storage.objects[job.request['reference_keys'][available.id]] == b'photo'
    assert response.json()['all_project_photos']
