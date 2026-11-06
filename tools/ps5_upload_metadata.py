#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Supplement a verified SC2 USB transfer with its exact provisional app metadata.

Local-only plan by default. No eboot replacement, installation or title launch.
"""
import argparse
import http.client
import json
from pathlib import Path
import re

from ps5_upload_usb import Wfm, sha256, plain

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private'
USB = '/mnt/usb0'
APP = USB + '/Soulcalibur II'
SYSTEM = APP + '/sce_sys'
TITLE_ID = 'PPSA77024'
CONTENT_LABEL = 'SOULCALIBUR20000'
CONTENT_ID = 'UP9000-' + TITLE_ID + '_00-' + CONTENT_LABEL
TITLE_NAME = 'Soulcalibur II'
PARAM_KEYS = {'ageLevel', 'applicationCategoryType', 'applicationDrmType', 'attribute', 'attribute2',
              'attribute3', 'conceptId', 'contentBadgeType', 'contentId', 'contentVersion',
              'downloadDataSize', 'gameIntent', 'localizedParameters', 'masterVersion',
              'requiredSystemSoftwareVersion', 'sdkVersion', 'titleId', 'versionFileUri'}


def unique_object(items):
    result = {}
    for name, value in items:
        if name in result:
            raise ValueError('duplicate JSON key: ' + name)
        result[name] = value
    return result


def bounded_json(path, limit):
    if not path.is_file() or not 1 <= path.stat().st_size <= limit:
        raise ValueError('missing/oversized JSON input: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_object)


def validate_param(path, expected_hash):
    path = plain(path)
    if not path.is_relative_to(PRIVATE.resolve()) or path.name != 'param.json':
        raise ValueError('metadata must be an existing private param.json')
    if not re.fullmatch('[0-9a-f]{64}', expected_hash) or sha256(path) != expected_hash:
        raise ValueError('param.json differs from selected metadata hash')
    value = bounded_json(path, 64 * 1024)
    if not isinstance(value, dict) or set(value) != PARAM_KEYS:
        raise ValueError('metadata must use the selected original PS5 parameter schema')
    if len(CONTENT_LABEL) != 16 or not re.fullmatch(r'UP[0-9]{4}-PPSA[0-9]{5}_00-[A-Z0-9]{16}', CONTENT_ID):
        raise ValueError('allocated homebrew content identity is malformed')
    if value.get('titleId') != TITLE_ID or value.get('contentId') != CONTENT_ID:
        raise ValueError('metadata does not match Cinder\'s provisional SC2 homebrew identity')
    localized = value.get('localizedParameters')
    if not isinstance(localized, dict) or localized.get('defaultLanguage') != 'en-US':
        raise ValueError('metadata needs the selected en-US title')
    if set(localized) != {'defaultLanguage', 'en-US'} or localized.get('en-US') != {'titleName': TITLE_NAME}:
        raise ValueError('metadata titleName must be Soulcalibur II without donor branding')
    raw = json.dumps(value, ensure_ascii=False).casefold()
    if any(text in raw for text in ('parasite eve', 'parasite-eve', 'ppsa77022', 'cpegametest')):
        raise ValueError('metadata contains unrelated PE identity fields')
    if value.get('applicationDrmType') != 'free' or value.get('versionFileUri') != '':
        raise ValueError('metadata must be free homebrew without an external version URL')
    if value.get('gameIntent') != {'permittedIntents': [{'intentType': 'launchActivity'}]}:
        raise ValueError('metadata launch intent differs from selected app schema')
    if not re.fullmatch(r'[0-9]{2}\.[0-9]{3}\.[0-9]{3}', str(value.get('contentVersion'))) or not re.fullmatch(r'[0-9]{2}\.[0-9]{2}', str(value.get('masterVersion'))):
        raise ValueError('metadata version strings are malformed')
    return path, value


def selected_upload(path):
    path = plain(path)
    if not path.is_relative_to(PRIVATE.resolve()):
        raise ValueError('selected upload receipt must remain private')
    stamp = sha256(path)
    value = bounded_json(path, 16 * 1024 * 1024)
    if (value.get('schema') != 'sc2.usb-transfer.v1' or value.get('state') != 'usb-transfer-verified' or
            value.get('mode') != 'files' or value.get('uploaded') is not True or
            value.get('all_files_transferred') is not True or value.get('destination') != USB):
        raise ValueError('require the completed verified direct-file upload receipt for USB0')
    if value.get('uploaded_files') != value.get('files') or isinstance(value.get('files'), bool) or not isinstance(value.get('files'), int) or value['files'] < 1:
        raise ValueError('upload receipt does not account for every package file')
    sizes = value.get('remote_sizes', {})
    if (sizes.get('verified') != 'all-file-sizes-and-directories' or sizes.get('file_count') != value['files'] or
            sizes.get('bytes') != value.get('uncompressed_bytes')):
        raise ValueError('upload receipt lacks complete remote size/directory verification')
    matches = [row for row in value.get('file_readbacks', []) if row.get('path') == APP + '/eboot.bin']
    if len(matches) != 1:
        raise ValueError('upload receipt needs exactly one verified SC2 eboot readback')
    eboot = matches[0]
    if (eboot.get('verified') != 'streamed-download-sha256' or
            isinstance(eboot.get('bytes'), bool) or not isinstance(eboot.get('bytes'), int) or not 64 <= eboot['bytes'] <= 1024 * 1024 * 1024 or
            not re.fullmatch('[0-9a-f]{64}', str(eboot.get('sha256')))):
        raise ValueError('upload receipt eboot identity is malformed')
    if sha256(path) != stamp:
        raise ValueError('selected upload receipt changed while reading')
    return path, stamp, eboot


def app_entries(wfm, eboot):
    entries = wfm.listing(APP)
    current = next((row for row in entries if row.get('name') == 'eboot.bin'), None)
    if not current or current.get('type') != '-' or current.get('size') != eboot['bytes']:
        raise ValueError('actual USB eboot type/size differs from verified base transfer')
    return entries


def system_state(wfm, app):
    matches = [row for row in app if row.get('name', '').casefold() == 'sce_sys']
    if not matches:
        return False
    if len(matches) != 1 or matches[0].get('name') != 'sce_sys' or matches[0].get('type') != 'd':
        raise ValueError('USB sce_sys path is not the exact ordinary app directory')
    if any(row.get('name', '').casefold() == 'param.json' for row in wfm.listing(SYSTEM)):
        raise ValueError('remote param.json already exists; no replacement is allowed')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--param', type=Path, required=True)
    parser.add_argument('--param-sha256', required=True)
    parser.add_argument('--upload-receipt', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True, help='fresh private receipt outside metadata source')
    parser.add_argument('--server', default='http://192.168.1.23:8888')
    parser.add_argument('--task-timeout', type=int, default=300)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    report = None
    try:
        if not 30 <= args.task_timeout <= 1800:
            raise ValueError('task timeout must be30–1800seconds')
        param, value = validate_param(args.param, args.param_sha256)
        upload, upload_hash, eboot = selected_upload(args.upload_receipt)
        output = plain(args.report)
        if not output.is_relative_to(PRIVATE.resolve()) or output.exists() or output.is_relative_to(param.parent):
            raise ValueError('report must be a fresh private file outside the metadata source')
        wfm = Wfm(args.server)
        report = dict(schema='sc2.usb-metadata.v1', state='local-plan-validated-no-network',
                      selected_upload=dict(path=str(upload), sha256=upload_hash),
                      param=dict(path=str(param), bytes=param.stat().st_size, sha256=args.param_sha256),
                      remote_app=APP, title_id=TITLE_ID, content_id=CONTENT_ID, title_name=TITLE_NAME,
                      identity_status='provisional homebrew allocation; not an official Sony reservation',
                      metadata_uploaded=False, installed=False, console_launched=False, gameplay_verified=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        def save(): output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        if not args.execute:
            save()
            print('SC2 metadata/local verified transfer preflight passed; no network operation.')
            return 0
        entries = app_entries(wfm, eboot)
        exists = system_state(wfm, entries)
        report['eboot_readback'] = wfm.readback(APP + '/eboot.bin', eboot['bytes'], eboot['sha256'], args.task_timeout)
        # Recheck source selection and absence immediately before any write.
        if sha256(upload) != upload_hash or sha256(param) != args.param_sha256:
            raise ValueError('selected upload receipt or metadata changed')
        exists = system_state(wfm, app_entries(wfm, eboot))
        if not exists:
            wfm.api('/api/mkdir', {'path': APP, 'name': 'sce_sys'})
            report['created_sce_sys'] = True
        # Upload inside sce_sys, so no existing app path participates in overwrite.
        if not system_state(wfm, app_entries(wfm, eboot)):
            raise ValueError('sce_sys directory was not created as expected')
        size = report['param']['bytes']
        task = wfm.api('/api/upload/prepare', dict(path=SYSTEM, src='param.json', count=1,
                       rels='param.json', sizes=str(size), total=size, overwrite='0'), form=True)
        task_id = task['task_id']
        report.update(state='uploading-new-parameter-json', upload_task_id=task_id)
        save()
        try:
            wfm.upload(task_id, SYSTEM, param, 'param.json', args.param_sha256, size)
            wfm.api('/api/upload/finish', {'task_id': task_id})
            report['upload_task'] = wfm.wait(task_id, args.task_timeout)
        except Exception:
            try:
                wfm.api('/api/cancel', {'id': task_id})
                wfm.api('/api/upload/finish', {'task_id': task_id})
            except Exception:
                pass
            raise
        report['param_readback'] = wfm.readback(SYSTEM + '/param.json', size, args.param_sha256, args.task_timeout)
        report.update(state='usb-metadata-verified', metadata_uploaded=True)
        save()
        print('New SC2 USB param.json SHA verified; eboot unchanged, no install or launch.')
        return 0
    except (ValueError, OSError, KeyError, TypeError, http.client.HTTPException) as error:
        if report is not None:
            report.update(state='failed-partial-state-preserved', error=str(error))
            output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        parser.exit(1, 'metadata supplement rejected/failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
