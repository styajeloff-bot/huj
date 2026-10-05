"""Isolated real-HTTP verification for task 22268; no external integrations."""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4, uuid5

ROOT = Path('/runtime')
HOST_ROOT = Path('/tmp/carcraft-22268-e2e')
MARKER = 'monetization-22268'
DEALER_NAME = 'Дилер «22268 Тестовый дилер»'


def identifier(name: str) -> UUID:
    return uuid5(UUID('a22a2226-8000-4000-8000-000000000001'), name)


def require(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def progress(stage: str, **values: object) -> None:
    print(json.dumps({'stage': stage, **values}, ensure_ascii=False, default=str), flush=True)


def private_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
    path.chmod(0o600)


def guard():
    from infrastructure.settings import settings
    require(settings.db_host == 'postgres' and settings.db_name == 'monetization22268', 'Refusing non-fixture DB')
    require(settings.jwt_keys_dir == '/runtime/jwt', 'Refusing non-fixture JWT keys')
    require(Path.cwd() == ROOT and not (ROOT / '.env').exists(), 'Refusing project dotenv')
    require(not settings.dadata_api_key and not settings.smsc_login and not settings.smtp_host and not settings.s3_secret_access_key, 'Refusing external credentials')
    return settings


def keys():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = ROOT / 'jwt'
    directory.mkdir(exist_ok=True, mode=0o700)
    if not (directory / 'e2e.pem').exists():
        key = ec.generate_private_key(ec.SECP256R1())
        (directory / 'e2e.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        (directory / 'e2e.pub.pem').write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    for path in directory.iterdir():
        path.chmod(0o600)
    progress('local_keys_ready')


def migrate(check: bool = False):
    guard()
    from alembic import command
    from alembic.config import Config
    config = Config('/app/alembic.ini')
    config.set_main_option('script_location', '/app/alembic')
    config.set_main_option('prepend_sys_path', '/app')
    command.upgrade(config, 'head')
    if check:
        command.check(config)
    progress('migration_complete', check=check)


def program_payload(name: str, source: str = 'platform', *, active: bool = False) -> dict:
    return {
        'name': name, 'leasing_company_id': str(identifier('leasing-company')),
        'dealer_company_id': str(identifier('company/dealer')),
        'distributor_company_id': str(identifier('company/distributor')),
        'period_start': '2026-01-01', 'period_end': '2030-12-31',
        'status': 'active' if active else 'inactive',
        'sources': [{'source_type': source,
            'expenses': [{'local_id': 'expense-1', 'participant_type': 'leasing', 'base_type': 'property_value', 'calc_type': 'percent', 'value': '2'}],
            'incomes': [
                {'local_id': 'income-dealer', 'participant_type': 'dealer', 'base_type': 'property_value', 'calc_type': 'percent', 'value': '1', 'expense_ref': 'expense-1'},
                {'local_id': 'income-distributor', 'participant_type': 'distributor', 'base_type': 'property_value', 'calc_type': 'percent', 'value': '0.6', 'expense_ref': 'expense-1'},
                {'local_id': 'income-platform', 'participant_type': 'platform', 'base_type': 'property_value', 'calc_type': 'percent', 'value': '0.4', 'expense_ref': 'expense-1'},
            ]}],
    }


class API:
    def __init__(self, state: dict):
        self.state = state
        self.checks = []

    async def request(self, role: str, method: str, path: str, expected: int | tuple[int, ...] = 200, **kwargs):
        import httpx
        actor = self.state['users'][role]
        async with httpx.AsyncClient(base_url='http://backend:3002', trust_env=False,
            cookies={'accessToken': actor['access_token'], 'csrfToken': actor['csrf']},
            headers={'X-CSRF-Token': actor['csrf'], 'Origin': 'http://localhost:18268'}, timeout=30) as client:
            response = await client.request(method, path, **kwargs)
        allowed = (expected,) if isinstance(expected, int) else expected
        require(response.status_code in allowed, f'{role} {method} {path}: HTTP {response.status_code}; {response.text[:800]}')
        return response.json() if response.content else None

    def passed(self, name: str):
        self.checks.append(name)
        progress('api_check_passed', check=name)


async def seed():
    settings = guard()
    import secrets
    from sqlalchemy import select, update
    from infrastructure.auth import generate_tokens, hash_refresh_token
    from infrastructure.crypto.key_configuration import load_and_validate_key_configuration
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import Company, LeasingCompany, DistributorDealerLink
    from infrastructure.models.users import User, UserCompany, UserSession
    from infrastructure.models.support import SupportProgram, SupportProgramDistributor
    from infrastructure.models.vehicles import Vehicle
    from infrastructure.models.exchange import ExchangeRequest, ExchangeBid
    from infrastructure.models import monetization as m
    from infrastructure.repositories import monetization_repository as repo
    from domain.monetization.programs import calculate_program
    from presentation.schemas.monetization import ProgramInput
    load_and_validate_key_configuration()
    state_path = ROOT / 'state.secret.json'
    if state_path.exists():
        state = json.loads(state_path.read_text())
        progress('resuming_fixture_seed')
    else:
        state = {'marker': MARKER, 'users': {}, 'companies': {}, 'supports': {}}
        async with AsyncSessionLocal() as session:
            require(await session.get(Company, identifier('company/dealer')) is None, 'Partial fixture needs investigation before retry')
            companies = {}
            for index, (name, kind, label) in enumerate([
                ('leasing_company', 'leasing_company', '22268 Тестовая лизинговая'),
                ('dealer', 'dealer', DEALER_NAME),
                ('distributor', 'distributor', '22268 Основной дистрибьютор'),
                ('second_distributor', 'distributor', '22268 Второй дистрибьютор'),
                ('client', 'other', '22268 Тестовый клиент'),
            ], 1):
                company = Company(id=identifier('company/' + name), name=label, inn=f'000022268{index}', company_type=kind, is_active=True)
                companies[name] = company
                session.add(company)
                state['companies'][name] = {'id': str(company.id), 'company_id': str(company.id), 'name': label, 'inn': company.inn}
            await session.flush()
            lc = LeasingCompany(id=identifier('leasing-company'), company_id=companies['leasing_company'].id, is_active=True)
            session.add(lc)
            state['companies']['leasing_company']['id'] = str(lc.id)
            users = {}
            role_specs = [('admin', 'carcraft_employee', None), ('dealer', 'dealer', 'dealer'), ('leasing', 'leasing_company', 'leasing_company'),
                ('distributor', 'distributor', 'distributor'), ('read_only', 'distributor', 'distributor'), ('outsider', 'distributor', 'second_distributor')]
            for index, (alias, role, company_name) in enumerate(role_specs, 1):
                user = User(id=identifier('user/' + alias), name='22268 synthetic ' + alias, phone=f'+700022268{index:02}',
                    email=alias+'@monetization22268.test', role=role, company_id=companies[company_name].id if company_name else None,
                    is_active=True, phone_verified=True, email_verified=True)
                users[alias] = user
                session.add(user)
            await session.flush()
            for alias, role, company_name in role_specs:
                user = users[alias]
                if company_name:
                    session.add(UserCompany(user_id=user.id, company_id=companies[company_name].id, sub_role='administrator' if alias!='read_only' else 'manager',
                        can_view_applications=True, can_create_applications=alias!='read_only'))
                sid = uuid4()
                access, refresh = generate_tokens(user.id, role, user.company_id, refresh_session_id=sid)
                session.add(UserSession(id=sid, user_id=user.id, refresh_token_hash=hash_refresh_token(refresh),
                    expires_at=datetime.now(UTC)+timedelta(days=1), ip_address='127.0.0.1', user_agent=MARKER))
                state['users'][alias] = {'id': str(user.id), 'role': role, 'company_id': str(user.company_id) if user.company_id else None,
                    'access_token': access, 'refresh_token': refresh, 'csrf': secrets.token_urlsafe(24)}
            session.add(DistributorDealerLink(distributor_company_id=companies['distributor'].id, dealer_company_id=companies['dealer'].id))
            for name, label, owner in [('direct', '22268 Поддержка основного', 'distributor'), ('multi', '22268 Общая поддержка', None), ('foreign', '22268 Чужая поддержка', 'second_distributor')]:
                support = SupportProgram(id=identifier('support/'+name), name=label, distributor_id=companies[owner].id if owner else None,
                    support_type='down_payment_compensation', support_params={}, starts_at=date(2026,1,1), ends_at=date(2030,12,31), is_active=True, created_by=users['admin'].id)
                session.add(support)
                state['supports'][name]={'id':str(support.id),'name':label}
            await session.flush()
            for name in ('distributor','second_distributor'):
                session.add(SupportProgramDistributor(support_program_id=identifier('support/multi'),distributor_id=companies[name].id))
            for name, number in [('ui', 2226801), ('api', 2226802)]:
                vehicle = Vehicle(id=identifier('vehicle/'+name), vin=f'E2E22268{name.upper():0<8}', dealer_id=companies['dealer'].id,
                    year=2026, base_price=Decimal('1000000'), status='available', is_available=True)
                session.add(vehicle)
                await session.flush()
                request = ExchangeRequest(id=identifier('request/'+name), lc_user_id=users['leasing'].id, lc_company_id=companies['leasing_company'].id,
                    vehicle_id=vehicle.id, quantity=1, status='open', batch_number=number, batch_index=1, expiration_at=datetime.now(UTC)+timedelta(days=30))
                session.add(request)
                await session.flush()
                session.add(ExchangeBid(id=identifier('bid/'+name), request_id=request.id, dealer_id=users['dealer'].id,
                    dealer_company_id=companies['dealer'].id, distributor_id=None, price=Decimal('1000000'), quantity=1,
                    kp_status='accepted', is_accepted=False))
            await session.commit()
        private_json(state_path, state)
        progress('synthetic_base_seeded', companies=len(state['companies']), actors=len(state['users']))
    # Keep resumed fixtures representative of the quoted dealer name reported
    # in task 22268 without recreating agreements.
    require(state['marker']==MARKER, 'Wrong fixture marker')
    require(state['companies']['dealer']['id']==str(identifier('company/dealer')), 'Unexpected dealer fixture identity')
    async with AsyncSessionLocal() as session:
        dealer=await session.get(Company,identifier('company/dealer'))
        require(dealer is not None and dealer.company_type=='dealer' and dealer.inn=='0000222682', 'Refusing to rename a non-fixture company')
        dealer.name=DEALER_NAME
        await session.commit()
    state['companies']['dealer']['name']=DEALER_NAME
    private_json(state_path,state)
    progress('synthetic_dealer_name_ready',name=DEALER_NAME)
    api = API(state)
    if not state.get('program_id'):
        payload = program_payload('22268 Synthetic exchange flow', 'exchange', active=True)
        created = await api.request('admin', 'POST', '/api/v1/admin/monetization/programs', 201, json=payload)
        require(created['rules_version']==2 and len(created['sources'][0]['incomes'])==3, 'New program lost v2 or incomes')
        state['program_id'] = created['id']
        private_json(state_path, state)
    for name in ('ui', 'api'):
        if not state.get(name+'_deal_id'):
            await api.request('leasing','PUT',f'/api/v1/exchange/bids/{identifier("bid/"+name)}/approve')
            async with AsyncSessionLocal() as session:
                rows = (await session.scalars(select(m.deals.c.id).where(m.deals.c.exchange_request_id==identifier('request/'+name)))).all()
            require(len(rows)==1, f'{name}: real exchange approval did not create exactly one deal')
            state[name+'_deal_id']=str(rows[0])
            private_json(state_path,state)
    if not state.get('legacy_deal_id'):
        raw=program_payload('22268 Legacy independent incomes','platform',active=True)
        raw['brand']='22268 LEGACY'
        raw['sources'][0]['incomes'][0].pop('expense_ref')
        raw['sources'][0]['incomes'][0]['value']='3'
        raw['sources'][0]['incomes']=raw['sources'][0]['incomes'][:1]
        raw['sources'].append(deepcopy(raw['sources'][0]))
        raw['sources'][1]['source_type']='dealer_account'
        payload=ProgramInput.model_validate(raw).model_dump()
        payload['rules_version']=1
        async with AsyncSessionLocal() as session:
            program=await repo.create_program(session,payload,identifier('user/admin'))
            context={'source_type':'platform','application_id':identifier('legacy-application'),
                'leasing_company_application_id':identifier('legacy-lca'),'application_number':'E2E-22268-LEGACY',
                'leasing_company_id':identifier('leasing-company'),'dealer_company_id':identifier('company/dealer'),
                'distributor_company_id':identifier('company/distributor'),'client_company_id':identifier('company/client'),
                'base_amount':Decimal('1000000'),'occurred_at':datetime.now(UTC),
                'vehicles':[{'vehicle_id':identifier('vehicle/ui'),'brand':'22268 LEGACY','quantity':1}],
                'actor_user_id':identifier('user/admin')}
            amounts=calculate_program(program,context)
            deal=await repo.insert_deal(session,context,program,amounts)
            await session.commit()
        state['legacy_deal_id']=str(deal['id'])
        state['legacy_program_id']=str(program['id'])
        private_json(state_path,state)
    # Existing deals display participant snapshots, so update only the name
    # metadata of the two guarded synthetic deals used by browser/API checks.
    async with AsyncSessionLocal() as session:
        for alias, number in (('ui','2226801-1'),('api','2226802-1')):
            deal_id=UUID(state[alias+'_deal_id'])
            predicate=(m.deals.c.id==deal_id) & (m.deals.c.application_number==number) & (m.deals.c.dealer_company_id==identifier('company/dealer'))
            current=(await session.execute(select(m.deals.c.participant_snapshot).where(predicate))).scalar_one_or_none()
            require(current is not None, 'Refusing to rename an unrecognized deal fixture')
            snapshot=deepcopy(current)
            require(snapshot['dealer_company']['id']==str(identifier('company/dealer')), 'Unexpected dealer in fixture participant snapshot')
            snapshot['dealer_company']['name']=DEALER_NAME
            await session.execute(update(m.deals).where(predicate).values(participant_snapshot=snapshot))
        await session.commit()
    storages={}
    for alias, user in state['users'].items():
        cookies=[]
        for key,value,httponly in [('accessToken',user['access_token'],True),('refreshToken',user['refresh_token'],True),('csrfToken',user['csrf'],False)]:
            cookies.append({'name':key,'value':value,'domain':'localhost','path':'/','expires':time.time()+86400,'httpOnly':httponly,'secure':False,'sameSite':'Lax'})
        filename=f'{alias}.storage.json'
        private_json(ROOT/filename,{'cookies':cookies,'origins':[]})
        storages[alias]=str(HOST_ROOT/filename)
    manifest={'marker':MARKER,'base_url':'http://localhost:18268','storage_states':storages,'companies':state['companies'],
        'support_program':state['supports']['direct'],'multi_distributor_support':state['supports']['multi'],
        'foreign_support_program':state['supports']['foreign'], 'deal_id':state['ui_deal_id'],'deal_application_number':'2226801-1',
        'confirmation_deal_id':state['ui_deal_id'],'confirmation_application_number':'2226801-1',
        'legacy_deal_id':state['legacy_deal_id'],'legacy_application_number':'E2E-22268-LEGACY'}
    private_json(ROOT/'manifest.json',manifest)
    progress('fixture_manifest_ready',path=str(HOST_ROOT/'manifest.json'),new_deal_count=2,legacy_deal_count=1)

async def verify_revoked_access(api: API, state: dict, deal_id: str, revision: int, document_id: UUID):
    from sqlalchemy import delete, insert, select, update
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import DistributorDealerLink
    from infrastructure.models.users import UserCompany
    distributor = identifier('company/distributor')
    dealer = identifier('company/dealer')
    table = DistributorDealerLink.__table__
    predicate = (table.c.distributor_company_id==distributor) & (table.c.dealer_company_id==dealer)
    async with AsyncSessionLocal() as session:
        saved = (await session.execute(select(table).where(predicate))).mappings().one()
        saved = dict(saved)
        await session.execute(delete(table).where(predicate))
        await session.commit()
    try:
        listing = await api.request('distributor','GET','/api/v1/monetization/deals')
        require(not any(row['id']==deal_id for row in listing['items']), 'Revoked direct link still grants list access')
        await api.request('distributor','GET','/api/v1/monetization/deals/'+deal_id,404)
        denied_file = await api.request('distributor','GET','/api/v1/monetization/files/deals/'+str(document_id),404)
        require(denied_file['detail']=='Документ не найден', 'Revoked file access reached object storage')
        await api.request('distributor','POST','/api/v1/monetization/deals/'+deal_id+'/confirm',404,json={'revision':revision})
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(insert(table).values(**saved))
            await session.commit()
    await api.request('distributor','GET','/api/v1/monetization/deals/'+deal_id)
    api.passed('revoked direct-only link denies list card confirmation and document before storage')

    table = UserCompany.__table__
    predicate = (table.c.user_id==identifier('user/distributor')) & (table.c.company_id==distributor)
    async with AsyncSessionLocal() as session:
        previous = await session.scalar(select(table.c.can_view_applications).where(predicate))
        require(previous is True, 'Revocation fixture lacks initial view permission')
        await session.execute(update(table).where(predicate).values(can_view_applications=False))
        await session.commit()
    try:
        await api.request('distributor','GET','/api/v1/monetization/deals',403)
        await api.request('distributor','GET','/api/v1/monetization/deals/'+deal_id,403)
        await api.request('distributor','GET','/api/v1/monetization/files/deals/'+str(document_id),403)
        await api.request('distributor','POST','/api/v1/monetization/deals/'+deal_id+'/confirm',403,json={'revision':revision})
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(update(table).where(predicate).values(can_view_applications=previous))
            await session.commit()
    await api.request('distributor','GET','/api/v1/monetization/deals/'+deal_id)
    api.passed('revoked company view denies list card confirmation and document')

async def verify_support_lookup(api: API, state: dict):
    chosen=state['companies']['distributor']['id']; other=state['companies']['second_distributor']['id']
    support_ids={name:item['id'] for name,item in state['supports'].items()}
    expected=set(support_ids.values())
    lookup='/api/v1/monetization/lookups/supports'
    no_selection=await api.request('admin','GET',lookup)
    require(expected <= {row['id'] for row in no_selection['items']}, 'Without distributor selection all accessible supports must be selectable')
    search=await api.request('admin','GET',lookup,params={'q':state['supports']['foreign']['name']})
    require({row['id'] for row in search['items']}=={support_ids['foreign']}, 'Support search without distributor lost its result')
    api.passed('support lookup and search without distributor show all accessible supports')
    own=await api.request('admin','GET',lookup,params={'distributor_company_id':chosen})
    own_ids={row['id'] for row in own['items']}
    require({support_ids['direct'],support_ids['multi']} <= own_ids and support_ids['foreign'] not in own_ids,'Support filter broken')
    foreign=await api.request('admin','GET',lookup,params={'distributor_company_id':other})
    other_ids={row['id'] for row in foreign['items']}
    require({support_ids['foreign'],support_ids['multi']} <= other_ids and support_ids['direct'] not in other_ids,'Multiple distributor lookup broken')
    api.passed('support lookup direct multiple and changed distributor')
    for role,visible in (
        ('distributor',{'direct','multi'}), ('read_only',{'direct','multi'}),
        ('dealer',{'direct','multi'}), ('outsider',{'foreign','multi'}),
        ('leasing',{'direct','foreign','multi'}),
    ):
        result=await api.request(role,'GET',lookup)
        found={row['id'] for row in result['items']} & expected
        require(found=={support_ids[name] for name in visible}, role+': optional distributor bypassed support visibility')
    restricted=await api.request('distributor','GET',lookup,params={'distributor_company_id':other})
    require(({row['id'] for row in restricted['items']} & expected)=={support_ids['multi']}, 'Explicit distributor filter bypassed actor visibility')
    api.passed('optional support filter preserves all role scopes and their intersection')


async def verify_supports():
    guard()
    state=json.loads((ROOT/'state.secret.json').read_text())
    require(state['marker']==MARKER, 'Wrong fixture marker')
    api=API(state)
    await verify_support_lookup(api,state)
    progress('support_e2e_complete',passed=len(api.checks))


async def verify():
    guard()
    from sqlalchemy import delete, func, insert, select, update
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models import monetization as m
    state = json.loads((ROOT/'state.secret.json').read_text())
    require(state['marker']==MARKER, 'Wrong fixture marker')
    # Reset only the dedicated synthetic API deal so retries exercise the same
    # pending-approval rules; the independently owned browser deal is untouched.
    async with AsyncSessionLocal() as session:
        result = await session.execute(update(m.deals).where(
            m.deals.c.id == UUID(state['api_deal_id']),
            m.deals.c.application_number == '2226802-1',
        ).values(status='pending_approval', confirmations={}))
        require(result.rowcount == 1, 'Refusing to reset an unrecognized API fixture')
        await session.commit()
    api = API(state)
    prefix = '22268 API ' + uuid4().hex[:8]

    async def create_case(name: str, payload: dict, status: int = 201):
        payload = deepcopy(payload)
        payload['name'] = prefix + ' ' + name
        async with AsyncSessionLocal() as session:
            before = await session.scalar(select(func.count()).select_from(m.programs).where(m.programs.c.name==payload['name']))
        result = await api.request('admin', 'POST', '/api/v1/admin/monetization/programs', status, json=payload)
        async with AsyncSessionLocal() as session:
            after = await session.scalar(select(func.count()).select_from(m.programs).where(m.programs.c.name==payload['name']))
        require(after-before == (1 if status==201 else 0), name+': partial/absent write')
        if status==201:
            require(result['rules_version']==2, name+': wrong server version')
        api.passed(name)
        return result

    base=program_payload(prefix)
    created=await create_case('one expense three universal linked incomes',base)
    source=created['sources'][0]
    require(len(source['expenses'])==1 and len(source['incomes'])==3, 'Multiple recipients lost')
    require(all(row['expense_ref']=='expense-1' for row in source['incomes']), 'Universal links not persisted')
    detail=await api.request('admin','GET','/api/v1/admin/monetization/programs/'+created['id'])
    require(detail['sources']==created['sources'], 'Reload changed conditions')
    payload=deepcopy(base); payload['sources']=[]
    await create_case('reject missing source',payload,400)
    payload=deepcopy(base); payload['sources'].append(deepcopy(payload['sources'][0]))
    payload['sources'][1]['source_type']='dealer_account'
    await create_case('reject multiple sources',payload,400)
    payload=deepcopy(base); payload['sources'][0]['incomes'][0].pop('expense_ref')
    await create_case('reject unlinked income',payload,400)
    payload=deepcopy(base); payload['sources'][0]['incomes'][0]['expense_ref']='another-source-expense'
    await create_case('reject foreign expense reference',payload,400)
    payload=deepcopy(base); payload['sources'][0]['incomes'][0]['value']='1.01'
    await create_case('reject total income exceeding expense',payload,400)
    payload=deepcopy(base); payload['rules_version']=1
    await create_case('reject client rules version injection',payload,422)
    payload=deepcopy(base); payload['support_program_id']=state['supports']['foreign']['id']
    await create_case('reject foreign distributor support',payload,400)
    payload=deepcopy(base); payload['support_program_id']=state['supports']['direct']['id']
    await create_case('accept direct distributor support',payload)
    payload=deepcopy(base); payload['support_program_id']=state['supports']['multi']['id']
    await create_case('accept multiple distributor support',payload)
    for support_name in ('direct','multi','foreign'):
        payload=deepcopy(base)
        payload.update(distributor_company_id=None, support_program_id=state['supports'][support_name]['id'], brand=prefix+' OPTIONAL '+support_name)
        optional=await create_case('accept '+support_name+' support without distributor',payload)
        require(optional['distributor_company_id'] is None and optional['support_program_id']==payload['support_program_id'], 'Optional distributor selection was not persisted')
        activated=await api.request('admin','PATCH','/api/v1/admin/monetization/programs/'+optional['id'],json={'status':'active'})
        require(activated['status']=='active' and activated['distributor_company_id'] is None and activated['support_program_id']==payload['support_program_id'], 'Support without distributor did not activate unchanged')
        api.passed('activate '+support_name+' support without distributor')
    payload=deepcopy(base)
    payload.update(distributor_company_id=None, support_program_id=str(uuid4()))
    await create_case('reject nonexistent support without distributor atomically',payload,400)
    await api.request('distributor','POST','/api/v1/admin/monetization/programs',403,json=payload)
    api.passed('optional distributor does not grant non-admin program creation')

    # Mutate only short-lived supports owned by this API run. Persistent browser
    # fixtures are never changed while testing reference removal and revocation.
    from infrastructure.models.support import SupportProgram
    for scenario in ('missing','foreign'):
        support_id=uuid4()
        async with AsyncSessionLocal() as session:
            session.add(SupportProgram(id=support_id, name=prefix+' activation '+scenario,
                distributor_id=identifier('company/distributor'), support_type='down_payment_compensation',
                support_params={}, starts_at=date(2026,1,1), ends_at=date(2030,12,31),
                is_active=True, created_by=identifier('user/admin')))
            await session.commit()
        try:
            payload=deepcopy(base)
            payload.update(support_program_id=str(support_id), brand=prefix+' REVOKED '+scenario)
            if scenario=='missing':
                payload['distributor_company_id']=None
            pending=await create_case('prepare '+scenario+' support activation',payload)
            async with AsyncSessionLocal() as session:
                if scenario=='missing':
                    await session.execute(delete(SupportProgram).where(SupportProgram.id==support_id))
                else:
                    await session.execute(update(SupportProgram).where(SupportProgram.id==support_id).values(distributor_id=identifier('company/second_distributor')))
                await session.commit()
            await api.request('admin','PATCH','/api/v1/admin/monetization/programs/'+pending['id'],400,json={'status':'active'})
            unchanged=await api.request('admin','GET','/api/v1/admin/monetization/programs/'+pending['id'])
            require(unchanged['status']=='inactive' and unchanged['sources']==pending['sources'], 'Invalid support activation partially changed conditions')
            api.passed('reject activation with '+scenario+' support atomically')
        finally:
            async with AsyncSessionLocal() as session:
                await session.execute(delete(SupportProgram).where(SupportProgram.id==support_id))
                await session.commit()

    overlap=deepcopy(base)
    overlap.update(status='active', brand=prefix+' OVERLAP')
    platform_program=await create_case('active platform source with unique brand',overlap)
    other_source=deepcopy(overlap)
    other_source['sources'][0]['source_type']='exchange'
    exchange_program=await create_case('allow same parameters different active source',other_source)
    require(platform_program['status']==exchange_program['status']=='active','Different sources did not both remain active')
    await create_case('reject same source active overlap without insertion',overlap,409)
    overlap['status']='inactive'
    inactive=await create_case('allow inactive same source overlap',overlap)
    await api.request('admin','PATCH','/api/v1/admin/monetization/programs/'+inactive['id'],409,json={'status':'active'})
    unchanged_program=await api.request('admin','GET','/api/v1/admin/monetization/programs/'+inactive['id'])
    require(unchanged_program['status']=='inactive' and unchanged_program['sources']==inactive['sources'], 'Failed conflicting activation partially changed program')
    async with AsyncSessionLocal() as session:
        active_count=await session.scalar(select(func.count()).select_from(m.programs).where(m.programs.c.brand==overlap['brand'],m.programs.c.status=='active'))
    require(active_count==2, 'Conflicting activation changed active set')
    api.passed('reject same source activation atomically while other sources stay active')

    rounded=deepcopy(base)
    rounded['sources'][0]={'source_type':'platform','expenses':[{'local_id':'e','participant_type':'leasing','base_type':'none','calc_type':'amount','value':'10'}],
        'incomes':[{'local_id':'i1','participant_type':'dealer','base_type':'none','calc_type':'amount','value':'5.50','expense_ref':'e'},
            {'local_id':'i2','participant_type':'distributor','base_type':'none','calc_type':'amount','value':'4.50','expense_ref':'e'}]}
    await create_case('accept exact kopecks 5.50 plus 4.50 equals 10',rounded)
    rounded['sources'][0]['incomes'][1]['value']='4.49'
    await create_case('accept exact kopecks 5.50 plus 4.49 below 10',rounded)
    fractional=deepcopy(rounded)
    fractional['sources'][0]['expenses'][0]['value']='0.10'
    fractional['sources'][0]['incomes'][0].update(base_type='expense_amount',calc_type='percent',value='55')
    fractional['sources'][0]['incomes'][1].update(base_type='expense_amount',calc_type='percent',value='45')
    await create_case('reject cent rounding 55 plus 45 percent of 0.10 as 0.06 plus 0.05',fractional,400)
    fractional['sources'][0]['incomes'][1]['value']='44.99'
    await create_case('accept cent rounding 55 plus 44.99 percent of 0.10 as 0.06 plus 0.04',fractional)
    bounded=deepcopy(rounded)
    bounded['sources'][0]['expenses'][0].update(value='20',max='10')
    await create_case('accept amount expense clipped by maximum',bounded)
    bounded['sources'][0]['incomes'][1]['value']='4.51'
    await create_case('reject income above clipped expense maximum',bounded,400)
    constants=deepcopy(base)
    constants['sources'][0]['expenses'][0].update(min='10',max='10')
    constants['sources'][0]['incomes']=constants['sources'][0]['incomes'][:2]
    for income in constants['sources'][0]['incomes']:
        income.update(base_type='expense_amount',value='50',min=None,max=None)
    await create_case('accept percent expense fixed by equal bounds and percent incomes',constants)
    constants['sources'][0]['incomes'][1]['value']='51'
    await create_case('reject percent incomes above fixed bounded expense',constants,400)
    constants['sources'][0]['incomes'][0].update(base_type='property_value',value='1',min='5.50',max='5.50')
    constants['sources'][0]['incomes'][1].update(base_type='property_value',value='1',min='4.50',max='4.50')
    await create_case('accept percent equal bounds 5.50 plus 4.50 equals 10',constants)
    constants['sources'][0]['incomes'][1].update(min='4.49',max='4.49')
    await create_case('accept percent equal bounds 5.50 plus 4.49 below 10',constants)
    minimum=deepcopy(base)
    minimum['sources'][0]['expenses'][0]['max']='10'
    minimum['sources'][0]['incomes']=minimum['sources'][0]['incomes'][:1]
    minimum['sources'][0]['incomes'][0]['min']='11'
    await create_case('reject minimum income exceeding maximum possible expense',minimum,400)

    mixed=deepcopy(base); mixed['sources'][0]['incomes']=mixed['sources'][0]['incomes'][:1]
    mixed['sources'][0]['incomes'][0].update(base_type='none',calc_type='amount',value='5000')
    await create_case('accept mixed formula pending actual deal value',mixed)
    two=deepcopy(base)
    second=deepcopy(two['sources'][0]['expenses'][0]); second['local_id']='expense-2'
    two['sources'][0]['expenses'].append(second)
    two['sources'][0]['incomes'].append({'local_id':'second-income','participant_type':'dealer','base_type':'expense_amount','calc_type':'percent','value':'100','expense_ref':'expense-2'})
    await create_case('accept two independent links one source',two)

    await verify_support_lookup(api, state)

    # Seed only the external source of a new synthetic deal. The real approve
    # HTTP command must select the existing exchange program and capture cents.
    from infrastructure.models.exchange import ExchangeRequest, ExchangeBid
    from infrastructure.models.vehicles import Vehicle
    vehicle_id, request_id, bid_id = uuid4(), uuid4(), uuid4()
    async with AsyncSessionLocal() as session:
        session.add(Vehicle(
            id=vehicle_id, vin='E2ECENT'+uuid4().hex[:10].upper(),
            dealer_id=identifier('company/dealer'), year=2026,
            base_price=Decimal('123456'), status='available', is_available=True,
        ))
        await session.flush()
        session.add(ExchangeRequest(
            id=request_id, lc_user_id=identifier('user/leasing'),
            lc_company_id=identifier('company/leasing_company'), vehicle_id=vehicle_id,
            quantity=1, status='open', batch_number=222680000+int(uuid4().hex[:6],16),
            batch_index=1, expiration_at=datetime.now(UTC)+timedelta(days=30),
        ))
        await session.flush()
        session.add(ExchangeBid(
            id=bid_id, request_id=request_id, dealer_id=identifier('user/dealer'),
            dealer_company_id=identifier('company/dealer'), distributor_id=None,
            price=Decimal('123456'), quantity=1, kp_status='accepted', is_accepted=False,
        ))
        await session.commit()
    await api.request('leasing','PUT',f'/api/v1/exchange/bids/{bid_id}/approve')
    async with AsyncSessionLocal() as session:
        captured_ids=(await session.scalars(select(m.deals.c.id).where(
            m.deals.c.exchange_request_id==request_id))).all()
    require(len(captured_ids)==1,'Cent exchange approval did not create exactly one deal')
    cent_deal=await api.request('admin','GET','/api/v1/monetization/deals/'+str(captured_ids[0]))
    expected_cents={'dealer':Decimal('1234.56'),'distributor':Decimal('740.74'),'platform':Decimal('493.82')}
    require(cent_deal['revision']==1 and Decimal(cent_deal['expenses'][0]['amount'])==Decimal('2469.12'),
            'New primary expense was not captured in kopecks')
    require({row['participant_type']:Decimal(row['amount']) for row in cent_deal['incomes']}==expected_cents,
            'New primary incomes were not rounded independently to kopecks')
    require(sum(expected_cents.values())==Decimal(cent_deal['expenses'][0]['amount']),
            'Cent primary capture exceeded its expense')
    api.passed('real HTTP exchange approval creates a fresh deal with 1234.56 income and cent budget')

    deal_id=state['api_deal_id']
    admin=await api.request('admin','GET','/api/v1/monetization/deals/'+deal_id)
    require(len(admin['expenses'])==1 and len(admin['incomes'])==3,'Actual exchange capture lost linked rows')
    require(sum(Decimal(row['amount']) for row in admin['incomes'])==Decimal(admin['expenses'][0]['amount']),'Actual capture budget mismatch')
    require(all(row['expense_ref_amount_id']==admin['expenses'][0]['id'] for row in admin['incomes']),'Capture lost linked amount IDs')
    api.passed('real HTTP exchange approve captures one expense and three incomes')
    await api.request('leasing','PUT',f'/api/v1/exchange/bids/{identifier("bid/api")}/approve',(400,409))
    async with AsyncSessionLocal() as session:
        count=await session.scalar(select(func.count()).select_from(m.deals).where(m.deals.c.exchange_request_id==identifier('request/api')))
    require(count==1,'Replay created a duplicate exchange deal')
    api.passed('repeated exchange approval creates no duplicate')

    def check_summary(item: dict):
        require(not {'expenses','incomes','amount','raw_amount'} & item.keys(), 'Financial rows leaked into list')
        for key in ('expense_participants','income_participants'):
            for row in item[key]:
                require(set(row)<={'participant_type','company'},'Money leaked in participant summary')
                if row['participant_type']!='platform':
                    require(row['company'] and row['company']['name'],'Company name missing')
    for role in ('admin','dealer','leasing','distributor','read_only'):
        listing=await api.request(role,'GET','/api/v1/monetization/deals',params={'page_size':100})
        target=next((row for row in listing['items'] if row['id']==deal_id),None)
        require(target is not None,role+': linked deal invisible')
        check_summary(target)
        if role!='admin':
            expected_party={'leasing':'leasing','read_only':'distributor'}.get(role,role)
            require(all(row['participant_type']==expected_party for row in target['expense_participants']+target['income_participants']),role+': other participant leaked')
        programs=await api.request(role,'GET','/api/v1/admin/monetization/programs',params={'page_size':100})
        require(all('sources' not in row for row in programs['items']),'Program financial rows leaked')
    api.passed('all roles list names without financial rows')
    outsider=await api.request('outsider','GET','/api/v1/monetization/deals')
    require(not any(row['id']==deal_id for row in outsider['items']),'Outsider saw deal')
    await api.request('outsider','GET','/api/v1/monetization/deals/'+deal_id,404)
    await api.request('outsider','POST','/api/v1/monetization/deals/'+deal_id+'/confirm',404,json={'revision':admin['revision']})
    readonly=await api.request('read_only','GET','/api/v1/monetization/deals/'+deal_id)
    require(not readonly['can_confirm'] and not readonly['can_upload_documents'],'Read-only action enabled')
    await api.request('read_only','POST','/api/v1/monetization/deals/'+deal_id+'/confirm',403,json={'revision':admin['revision']})
    api.passed('outsider denied and read-only cannot confirm')
    # A real metadata row with a nonempty object key lets denied HTTP requests
    # prove authorization stops before S3. No successful download is asserted.
    document_id=uuid4()
    async with AsyncSessionLocal() as session:
        await session.execute(insert(m.documents).values(
            id=document_id,deal_id=UUID(deal_id),participant_type='distributor',
            participant_company_id=identifier('company/distributor'),
            object_key='monetization/e2e-authorization/'+str(document_id),
            filename='22268-access-check.txt',content_type='text/plain',size_bytes=1,
            revision=admin['revision'],created_by=identifier('user/distributor')))
        await session.commit()
    try:
        visible=await api.request('distributor','GET','/api/v1/monetization/deals/'+deal_id)
        require(any(doc['id']==str(document_id) for doc in visible['documents']), 'Document metadata not visible before revocation')
        await verify_revoked_access(api, state, deal_id, admin['revision'], document_id)
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(m.documents).where(m.documents.c.id==document_id))
            await session.commit()
    adjustment={'revision':admin['revision'],'items':[{'deal_participant_amount_id':admin['incomes'][0]['id'],'new_value':'30000'}]}
    await api.request('admin','POST','/api/v1/admin/monetization/deals/'+deal_id+'/adjust-conditions',409,json=adjustment)
    unchanged=await api.request('admin','GET','/api/v1/monetization/deals/'+deal_id)
    require(unchanged['revision']==admin['revision'] and unchanged['incomes']==admin['incomes'],'Invalid adjustment partially applied')
    api.passed('deal adjustment budget rejected atomically')

    legacy=await api.request('admin','GET','/api/v1/monetization/deals/'+state['legacy_deal_id'])
    legacy_program=await api.request('admin','GET','/api/v1/admin/monetization/programs/'+state['legacy_program_id'])
    require(legacy_program['rules_version']==1 and len(legacy_program['sources'])==2,'Legacy rules not retained')
    require(any(row['expense_ref_amount_id'] is None for row in legacy['incomes']),'Legacy independent income changed')
    require(sum(Decimal(row['amount']) for row in legacy['incomes'])>sum(Decimal(row['amount']) for row in legacy['expenses']),'Legacy fixture did not preserve pre-existing semantics')
    await api.request('admin','PATCH','/api/v1/admin/monetization/programs/'+state['legacy_program_id'],json={'status':'inactive'})
    await api.request('admin','PATCH','/api/v1/admin/monetization/programs/'+state['legacy_program_id'],json={'status':'active'})
    after=await api.request('admin','GET','/api/v1/monetization/deals/'+state['legacy_deal_id'])
    require(after['expenses']==legacy['expenses'] and after['incomes']==legacy['incomes'],'Legacy toggling recalculated financial snapshot')
    api.passed('legacy independent income multiple sources and snapshot preserved')

    if admin['status']=='pending_approval':
        await api.request('admin','POST','/api/v1/admin/monetization/deals/'+deal_id+'/confirm',409,json={'revision':admin['revision']})
        for role in ('leasing','dealer','distributor'):
            result=await api.request(role,'POST','/api/v1/monetization/deals/'+deal_id+'/confirm',json={'revision':admin['revision']})
            require(not result['can_confirm'],'Confirmation still offered')
        await api.request('distributor','POST','/api/v1/monetization/deals/'+deal_id+'/confirm',409,json={'revision':admin['revision']})
        paid=await api.request('admin','POST','/api/v1/admin/monetization/deals/'+deal_id+'/confirm',json={'revision':admin['revision']})
        require(paid['status']=='paid','Final admin approval did not finish')
    api.passed('participant confirmation once then final administrator approval')
    private_json(ROOT/'results.json',{'marker':MARKER,'passed':api.checks,'count':len(api.checks),'completed_at':datetime.now(UTC)})
    progress('api_e2e_complete',passed=len(api.checks))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['keys', 'migrate', 'check', 'seed', 'verify', 'verify-supports'])
    args = parser.parse_args()
    if args.action == 'keys':
        keys()
    elif args.action in {'migrate', 'check'}:
        migrate(args.action == 'check')
    elif args.action == 'verify-supports':
        asyncio.run(verify_supports())
    else:
        asyncio.run(seed() if args.action == 'seed' else verify())
