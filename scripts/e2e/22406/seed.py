"""Task 22406 baseline fixture adapted to the current equipment catalog."""
import json
import time
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from runtime import (
    API, DEALER_NAME, MARKER, ROOT, guard, identifier, private_json,
    program_payload, progress, require,
)

HOST_ROOT = Path("/tmp/carcraft-22406-e2e")


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
    from infrastructure.models.special_equipment import SpecialEquipmentMark, SpecialEquipmentModel, SpecialEquipmentModification, SpecialEquipmentProduct
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
        require(state['marker'] == MARKER, 'Wrong fixture marker')
        async with AsyncSessionLocal() as session:
            for alias, actor in state['users'].items():
                require(actor['id'] == str(identifier('user/' + alias)), 'Unexpected fixture user')
                user = await session.get(User, UUID(actor['id']))
                require(user is not None, 'Fixture user missing')
                sid = uuid4()
                access, refresh = generate_tokens(user.id, user.role, user.company_id, refresh_session_id=sid)
                session.add(UserSession(id=sid, user_id=user.id, refresh_token_hash=hash_refresh_token(refresh),
                    expires_at=datetime.now(UTC)+timedelta(days=1), ip_address='127.0.0.1', user_agent=MARKER))
                actor.update(access_token=access, refresh_token=refresh, csrf=secrets.token_urlsafe(24))
            await session.commit()
        private_json(state_path, state)
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
                    session.add(UserCompany(user_id=user.id, company_id=companies[company_name].id, role=role, sub_role='administrator' if alias!='read_only' else 'manager',
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
            mark = SpecialEquipmentMark(id=identifier('catalog/mark'), code='22406-base', slug='22406-base', name='22406 Базовая марка')
            session.add(mark)
            await session.flush()
            model = SpecialEquipmentModel(id=identifier('catalog/model'), mark_id=mark.id, code='22406-base', slug='22406-base', name='22406 Базовая модель')
            session.add(model)
            await session.flush()
            modification = SpecialEquipmentModification(id=identifier('catalog/modification'), model_id=model.id, code='22406-base', slug='22406-base', name='22406 Базовая модификация')
            session.add(modification)
            await session.flush()
            state['catalog'] = {'mark_id': str(mark.id), 'model_id': str(model.id), 'modification_id': str(modification.id), 'brand': mark.name, 'model': model.name}

            for name, number in [('ui', 2226801), ('api', 2226802)]:
                vehicle = SpecialEquipmentProduct(id=identifier('vehicle/'+name), code='22406-'+name, slug='22406-'+name, modification_id=modification.id, vin=f'E2E22268{name.upper():0<8}', seller_company_id=companies['dealer'].id,
                    manufacture_year=2026, price=Decimal('1000000'), condition='new')
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
