import base64
from unittest.mock import Mock

import pytest

from app.ai.omni_provider import MODEL, OmniProvider
from app.ai.veo_provider import VideoFailure


@pytest.mark.parametrize('seconds', [4, 6, 8])
@pytest.mark.parametrize('mode', ['text', 'frame', 'references'])
def test_omni_submission(seconds, mode, tmp_path):
    image = tmp_path / 'photo.png'
    image.write_bytes(b'png')
    provider = object.__new__(OmniProvider)
    provider.api = Mock(return_value={'id': 'v1_test', 'status': 'in_progress'})
    operation = provider.submit('Action', 'Characters', image if mode == 'frame' else None,
                                [image] if mode == 'references' else [], seconds)
    assert operation == 'interactions/v1_test'
    args, kwargs = provider.api.call_args
    assert args == ('POST', '/interactions')
    body = kwargs['json']
    assert body['model'] == MODEL and body['background'] and body['store']
    assert body['response_format']['resolution'] == '720p'
    assert f'{seconds}-second' in body['input'][-1]['text']
    if mode != 'text':
        assert base64.b64decode(body['input'][0]['data']) == b'png'
    assert 'durationSeconds' not in str(body)


@pytest.mark.parametrize("mime_fields", [{}, {"mime_type": "video/mp4"}])
def test_poll_resume_and_inline_video(tmp_path, mime_fields):
    provider = object.__new__(OmniProvider)
    provider.api = Mock(side_effect=[{'status': 'in_progress'}, {'status': 'completed', 'steps': [
        {'type': 'model_output', 'content': [{'type': 'video', **mime_fields,
                                            'data': base64.b64encode(b'video').decode()}]}
    ]}])
    assert provider.poll('interactions/v1_test') is None
    output = tmp_path / 'out.mp4'
    provider.download(provider.poll('interactions/v1_test'), output)
    assert output.read_bytes() == b'video'
    assert provider.api.call_args.args == ('GET', '/interactions/v1_test')


@pytest.mark.parametrize('result', [{'status': 'failed'}, {'status': 'cancelled'},
                                   {'status': 'completed', 'steps': []}])
def test_failed_or_missing_output(result):
    provider = object.__new__(OmniProvider)
    provider.api = Mock(return_value=result)
    with pytest.raises(VideoFailure):
        provider.poll('interactions/v1_test')
    with pytest.raises(VideoFailure):
        provider.poll('interactions/../../secret')
