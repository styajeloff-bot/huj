"""Seed and verify the isolated warehouse form/migration E2E database."""
import asyncio
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import text

from infrastructure.auth import generate_tokens, hash_refresh_token
from infrastructure.database import AsyncSessionLocal
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentCategory, SpecialEquipmentMark, SpecialEquipmentModel,
    SpecialEquipmentModification, SpecialEquipmentModificationCategory,
)
from infrastructure.models.users import User, UserSession
from infrastructure.models.vehicles import City
from infrastructure.settings import settings


def uid(key):
    return uuid5(NAMESPACE_URL, 'warehouse-form-e2e/' + key)


async def main():
    if 'warehouse_form_e2e' not in settings.database_dsn:
        raise RuntimeError('Only the isolated warehouse form E2E database is permitted')
    async with AsyncSessionLocal() as session:
        if '--legacy' in sys.argv:
            session.add(Company(id=uid('owner'), name='E2E Складовладелец', inn='7000184181', company_type='dealer', is_active=True))
            session.add(SpecialEquipmentMark(id=uid('alpha'), code='wh-alpha', slug='wh-alpha', name='E2E Альфа'))
            await session.flush()
            for name, brand in [('legacy', uid('alpha')), ('empty', None)]:
                await session.execute(text('INSERT INTO warehouses (id,name,owner_company_id,owner_company_type,address,brand_id,is_active) VALUES (:id,:name,:owner,\'dealer\',\'E2E migration address\',:brand,true)'), {'id': uid(name), 'name': 'E2E ' + name, 'owner': uid('owner'), 'brand': brand})
            await session.commit()
            print('Legacy164 fixtures ready')
            return
        migrated = (await session.execute(text('SELECT warehouse_id,mark_id FROM warehouse_marks'))).all()
        assert migrated == [(uid('legacy'), uid('alpha'))], migrated
        assert await session.scalar(text('SELECT count(*) FROM warehouses WHERE category_id IS NOT NULL')) == 0
        assert await session.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_name='warehouses' AND column_name='brand_id'")) == 0
        print('Migration164→165 preserved legacy selection and empty warehouse')
        session.add(City(id=uid('city'), name='E2E Тестоград'))
        session.add(Company(id=uid('distributor-company'), name='E2E Дистрибьютор', inn='7000184182', company_type='distributor', is_active=True))
        for key, name, active in [('beta','E2E Бета',True), ('empty-mark','E2E Без моделей',True), ('inactive','E2E Неактивная',False), ('cascade','E2E Каскадная',True), ('shared','E2E Общая',True)]:
            session.add(SpecialEquipmentMark(id=uid(key), code='wh-' + key, slug='wh-' + key, name=name, is_active=active))
        for key, name, active in [('direct','E2E Прямая',True), ('mod','E2E Модификаций',True), ('beta-cat','E2E Бета категория',True), ('unrelated','E2E Посторонняя',True), ('inactive-cat','E2E Скрытая',False)]:
            session.add(SpecialEquipmentCategory(id=uid(key), code='wh-' + key, slug='wh-' + key, name=name, usage_metric='mileage_km', is_active=active, is_visible_in_catalog=False))
        await session.flush()
        for key, mark, category, active in [('alpha-model','alpha','direct',True), ('beta-model','beta','beta-cat',True), ('inactive-model','beta','unrelated',False)]:
            session.add(SpecialEquipmentModel(id=uid(key), code='wh-' + key, slug='wh-' + key, name='E2E ' + key, mark_id=uid(mark), category_id=uid(category), is_active=active))
        await session.flush()
        for key, model, active in [('alpha-mod','alpha-model',True), ('inactive-mod','beta-model',False)]:
            session.add(SpecialEquipmentModification(id=uid(key), code='wh-' + key, slug='wh-' + key, name='E2E ' + key, model_id=uid(model), is_active=active))
        await session.flush()
        for order, (mod, category) in enumerate([('alpha-mod','direct'), ('alpha-mod','mod'), ('alpha-mod','inactive-cat'), ('inactive-mod','unrelated')]):
            session.add(SpecialEquipmentModificationCategory(modification_id=uid(mod), category_id=uid(category), sort_order=order))
        output = Path('/runtime/artifacts')
        output.mkdir(parents=True, exist_ok=True)
        for index, (alias, role) in enumerate([('employee','carcraft_employee'), ('dealer','dealer'), ('distributor','distributor'), ('client','client')]):
            user = User(id=uid(alias), name='E2E ' + alias, phone='+7000184180' + str(index), role=role, is_active=True, phone_verified=True, mfa_enabled=False, company_id=uid('owner') if alias == 'dealer' else uid('distributor-company') if alias == 'distributor' else None)
            session.add(user)
            await session.flush()
            sid = uuid4()
            access, refresh = generate_tokens(user.id, role, user.company_id, refresh_session_id=sid)
            session.add(UserSession(id=sid, user_id=user.id, refresh_token_hash=hash_refresh_token(refresh), expires_at=datetime.now(UTC) + timedelta(days=1)))
            state = {'cookies': [{'name': key, 'value': value, 'domain': 'localhost', 'path': '/', 'expires': time.time()+86400, 'httpOnly': True, 'secure': False, 'sameSite': 'Lax'} for key, value in [('accessToken',access), ('refreshToken',refresh)]], 'origins': []}
            (output / (alias + '.storage.json')).write_text(json.dumps(state))
        await session.commit()
        keys = ['owner','city','alpha','beta','empty-mark','inactive','cascade','shared','direct','mod','beta-cat','unrelated','inactive-cat','legacy','empty']
        (output / 'manifest.json').write_text(json.dumps({key:str(uid(key)) for key in keys}))
        print('Warehouse form fixture ready')


asyncio.run(main())
