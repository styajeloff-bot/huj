import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { compileScript, parse } from '@vue/compiler-sfc'
import { ModuleKind, ScriptTarget, transpileModule } from 'typescript'
import { expect, test, type Page } from '@playwright/test'

const root = resolve(__dirname, '../../..')
const transpile = (source: string) => transpileModule(source.replaceAll('import.meta.client', 'true'), {
  compilerOptions: { target: ScriptTarget.ES2022, module: ModuleKind.CommonJS },
}).outputText
const sfc = (path: string) => {
  const filename = resolve(root, path)
  const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
  return transpile(compileScript(descriptor, { id: path, inlineTemplate: true }).content)
}
const sources = {
  modal: sfc('components/ui/Modal.vue'),
  isolation: transpile(readFileSync(resolve(root, 'components/ui/modalIsolation.ts'), 'utf8')),
  ...Object.fromEntries(['grouping', 'money', 'dealTerms'].map(name => [
    name, transpile(readFileSync(resolve(root, 'features/monetization/' + name + '.ts'), 'utf8')),
  ])),
  ...Object.fromEntries(['FileList', 'FileDropzone', 'DealAmount', 'DealDetail'].map(name => [
    name, sfc('features/monetization/components/' + name + '.vue'),
  ])),
}

// Actual monetization components and Modal run in Chromium. This focused browser
// harness replaces HTTP only; the separate real-app scenarios verify persistence.
async function mountDeal(page: Page) {
  await page.setContent('<style>' +
    '.fixed{position:fixed}.inset-0{inset:0}[class*="z-["]{z-index:230}' +
    '.flex{display:flex}.items-center{align-items:center}.justify-center{justify-content:center}' +
    '.min-h-full{min-height:100%}.relative{position:relative}.p-4{padding:16px}' +
    '[role=dialog]{box-sizing:border-box;max-height:90vh;overflow:auto;background:white;border:1px solid gray;padding:20px}' +
    '.contract-file-input{display:none}button,input{box-sizing:border-box;font:14px Arial;padding:6px;margin:4px 0}' +
    '</style><div id="__nuxt"></div>')
  await page.addStyleTag({ content: readFileSync(resolve(root, 'features/monetization/monetization.css'), 'utf8') })
  await page.addScriptTag({ path: require.resolve('vue/dist/vue.global.js') })
  await page.evaluate('(() => {' +
    'const sources = ' + JSON.stringify(sources) + ';' + String.raw`
    const modules = {};
    const load = source => new Function('Vue', 'require', 'const exports={}; with(Vue){' + source + '}; return exports;')(Vue, id => {
      if(id === 'vue') return Vue;
      if(id === '@heroicons/vue/24/outline') return {XMarkIcon:()=>Vue.h('span','×')};
      if(id === '~/features/storefront') return {useStorefrontTeleportContext:()=>({inheritedColors:{},teleportReady:Vue.ref(true)})};
      if(id === '../api') return {errorMessage:error=>error?.data?.detail || 'Ошибка запроса'};
      if(id === '../editor') return {participantLabels:{leasing:'ЛК',dealer:'Дилер',distributor:'Дистрибьютор',platform:'Платформа МЛ'},sourceLabel:()=> 'Заявка через платформу'};
      if(id in modules) return modules[id];
      throw new Error('Missing browser dependency: '+id);
    });
    modules['./modalIsolation'] = load(sources.isolation);
    for(const name of ['money','grouping','dealTerms']) modules['./'+name] = modules['../'+name] = load(sources[name]);
    modules['~/components/ui/Modal.vue'] = load(sources.modal);
    for(const name of ['FileList','FileDropzone','DealAmount','DealDetail']) modules['./'+name+'.vue'] = load(sources[name]);
    const confirmation = {applicable:true,confirmed_at:null,confirmed_by_name:null};
    const row = (id,amount,participant_type,expense_ref_amount_id=null,extra={}) => ({
      id,amount,participant_type,expense_ref_amount_id,raw_amount:amount,clip:'none',vat_excluded:false,
      original_amount:amount,original_percent:'10',original_calc_type:'percent',percent:modules['../money'].decimalString((modules['../money'].decimalUnits(amount)+BigInt(5))/BigInt(10)),
      input_mode:'amount',base_type:'property_value',calculation_base_amount:'1000',has_new_conditions:false,...extra,
    });
    const state = Vue.reactive({open:false,clicks:0,calls:[],failure:null,role:'carcraft_employee',deal:{
      id:'00000000-0000-4000-8000-000000000001',application_number:'22268',source_type:'platform',
      status:'pending_approval',revision:1,base_amount:'1000',program_name:'Условия',created_at:'2026-09-16T09:00:00Z',
      has_new_conditions:false,can_adjust:true,can_confirm:false,can_upload_documents:true,documents:[],
      expenses:[row('00000000-0000-4000-8000-000000000002','100','leasing')],incomes:[],
      confirmations:{leasing:{...confirmation},dealer:{...confirmation},distributor:{...confirmation,applicable:false}},
    }});
    const api = {
      deal:async()=>state.deal,
      adjust:async(id,revision,items)=>{
        state.calls.push({id,revision,items});
        if(state.failure) throw {statusCode:state.failure,data:{detail:'Условия сделки уже изменились'}};
        const drafts = modules['../dealTerms'].createTermsDraft(state.deal);
        for(const item of items) drafts[item.deal_participant_amount_id] = {inputMode:item.input_mode,value:item.input_mode === 'percent' ? item.new_percent : item.new_value,dirty:true};
        const preview = modules['../dealTerms'].previewDealTerms(state.deal,drafts);
        const update = row => {
          const value = preview.rows[row.id];
          return {...row,amount:value.finalAmount,percent:value.effectivePercent,input_mode:value.inputMode,
            calculation_base_amount:value.base,has_new_conditions:row.has_new_conditions || value.changed};
        };
        return {...state.deal,revision:revision+1,has_new_conditions:true,
          expenses:state.deal.expenses.map(update),incomes:state.deal.incomes.map(update)};
      },
    };
    window.monetizationModalState = state;
    window.monetizationRow = row;
    Vue.createApp({render:()=>Vue.h('div',[
      Vue.h('button',{id:'open-deal',onClick:()=>state.open=true},'Открыть сделку'),
      Vue.h('button',{id:'background-action',onClick:()=>state.clicks++},'Действие страницы'),
      Vue.h('output',{id:'updated-amount'},state.deal.expenses[0].amount),
      state.open ? Vue.h(modules['./DealDetail.vue'].default,{api,deal:state.deal,role:state.role,onClose:()=>state.open=false,onUpdated:deal=>state.deal=deal}) : null,
    ])}).mount('#__nuxt');
  })()`)
  await page.getByRole('button', { name: 'Открыть сделку', exact: true }).click()
  await expect(parentDialog(page)).toBeVisible()
}
const parentDialog = (page: Page) => page.getByRole('dialog', { name: 'Сделка 22268', exact: true })
const amount = (page: Page, index = 0) => parentDialog(page).locator('.deal-amount').nth(index)
async function openAdjustment(page: Page) {
  await parentDialog(page).getByRole('button', { name: 'Изменить суммы', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(1)
  await expect(parentDialog(page).locator('.deal-terms-editor').first()).toBeVisible()
}

test('inline editing keeps one focus-trapped modal and cancelling restores its edit trigger', async ({ page }) => {
  await mountDeal(page)
  await openAdjustment(page)
  const modal = parentDialog(page)
  await expect(amount(page).getByLabel('Процент', { exact: true })).toBeFocused()
  await expect(modal.getByRole('button', { name: 'Обновить', exact: true })).toBeDisabled()
  const controls = modal.locator('button:not([disabled]), input:not([disabled])')
  await controls.last().focus()
  await page.keyboard.press('Tab')
  await expect(controls.first()).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(controls.last()).toBeFocused()
  await modal.getByRole('button', { name: 'Отмена', exact: true }).click()
  await expect(modal.locator('.deal-terms-editor')).toHaveCount(0)
  await expect(modal.getByRole('button', { name: 'Изменить суммы', exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.locator('#open-deal')).toBeFocused()
  await expect(page.locator('#__nuxt')).not.toHaveAttribute('inert', '')
})

test('unmounting an inline editor restores page interactivity and scroll', async ({ page }) => {
  await mountDeal(page)
  await openAdjustment(page)
  await page.evaluate('window.monetizationModalState.open = false')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.locator('#__nuxt')).not.toHaveAttribute('inert', '')
  await expect(page.locator('#__nuxt')).not.toHaveAttribute('aria-hidden', 'true')
  await expect.poll(() => page.locator('body').evaluate(el => getComputedStyle(el).overflow)).not.toBe('hidden')
  await page.locator('#background-action').click()
  await expect.poll(() => page.evaluate('window.monetizationModalState.clicks')).toBe(1)
})

test('new amount input previews cents without changing typing, normalizes on blur and persists', async ({ page }) => {
  await mountDeal(page)
  await openAdjustment(page)
  const money = amount(page).getByLabel('Сумма, ₽', { exact: true })
  await money.fill('125,505')
  await expect(money).toHaveValue('125,505')
  await expect(amount(page).getByLabel('Процент', { exact: true })).toHaveValue('12.55')
  await expect(amount(page).locator('.deal-terms-editor')).toContainText('Итого: 125,51 ₽')
  await amount(page).getByLabel('Процент', { exact: true }).focus()
  await expect(money).toHaveValue('125.51')
  await parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(parentDialog(page).locator('.deal-terms-editor')).toHaveCount(0)
  await expect(amount(page).locator('.deal-original-terms')).toContainText('100 ₽')
  await expect(amount(page).locator('.deal-new-terms')).toContainText('125,51 ₽')
  await expect(page.locator('#updated-amount')).toHaveText('125.51')
  expect(await page.evaluate('window.monetizationModalState.calls')).toEqual([{
    id: '00000000-0000-4000-8000-000000000001', revision: 1,
    items: [{ deal_participant_amount_id: '00000000-0000-4000-8000-000000000002', input_mode: 'amount', new_value: '125.51' }],
  }])
})

test('Enter saves a normalized percent and matching cents without requiring blur', async ({ page }) => {
  await mountDeal(page)
  await openAdjustment(page)
  const percent = amount(page).getByLabel('Процент', { exact: true })
  await percent.fill('23.38743238')
  await expect(percent).toHaveValue('23.38743238')
  await expect(amount(page).getByLabel('Сумма, ₽', { exact: true })).toHaveValue('233.9')
  await percent.press('Enter')
  await expect(amount(page).locator('.deal-new-terms')).toContainText('23,39%')
  await expect(page.locator('#updated-amount')).toHaveText('233.9')
  expect(await page.evaluate('window.monetizationModalState.calls[0].items[0].new_percent')).toBe('23.38743238')
  await openAdjustment(page)
  await expect(percent).toHaveValue('23.39')
  await expect(parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled()
})

test('historic whole-ruble terms stay unchanged until their percent is explicitly entered', async ({ page }) => {
  await mountDeal(page)
  await page.evaluate(String.raw`(() => {
    const state = window.monetizationModalState;
    state.deal = {...state.deal,base_amount:'123456',expenses:[window.monetizationRow('historic','1235','leasing',null,{
      percent:'1',original_percent:'1',input_mode:'percent',calculation_base_amount:'123456'
    })]};
  })()`)
  await openAdjustment(page)
  const percent = amount(page).getByLabel('Процент', { exact: true })
  const money = amount(page).getByLabel('Сумма, ₽', { exact: true })
  await money.focus()
  await percent.focus()
  await expect(money).toHaveValue('1235')
  await expect(parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled()
  await percent.fill('1')
  await expect(money).toHaveValue('1234.56')
  await parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(page.locator('#updated-amount')).toHaveText('1234.56')
  await expect(amount(page).locator('.deal-original-terms')).toContainText('1 235 ₽')
})

test('historical precise rates survive focus, repeated money and unrelated edits', async ({ page }) => {
  await mountDeal(page)
  await page.evaluate(String.raw`(() => {
    const state = window.monetizationModalState;
    const original = state.deal.expenses[0];
    state.deal = {...state.deal,expenses:[{...original,percent:'10.00000001'},
      window.monetizationRow('other','20','leasing',null,{percent:'2'})]};
  })()`)
  await openAdjustment(page)
  await expect(amount(page).getByLabel('Процент', { exact: true })).toHaveValue('10')
  await amount(page).getByLabel('Сумма, ₽', { exact: true }).fill('100')
  await expect(parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled()
  await amount(page, 1).getByLabel('Сумма, ₽', { exact: true }).fill('21')
  await parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true }).click()
  expect(await page.evaluate('window.monetizationModalState.calls[0].items.map(item=>item.deal_participant_amount_id)')).toEqual(['other'])
  expect(await page.evaluate('window.monetizationModalState.deal.expenses[0].percent')).toBe('10.00000001')
})

test('positive cent remainder is informational, disappears at zero and hides for invalid groups', async ({ page }) => {
  await mountDeal(page)
  await page.evaluate(String.raw`(() => {
    const state = window.monetizationModalState;
    state.deal = {...state.deal,incomes:[window.monetizationRow('income','99','dealer',state.deal.expenses[0].id,{percent:'9.9'})]};
  })()`)
  await expect(parentDialog(page).locator('.deal-budget-remaining')).toHaveCount(0)
  await openAdjustment(page)
  const remainder = parentDialog(page).locator('.deal-budget-remaining')
  await expect(remainder).toHaveText('Осталась не распределенная сумма 1 ₽')
  await amount(page, 0).getByLabel('Сумма, ₽', { exact: true }).fill('100.49')
  await amount(page, 1).getByLabel('Сумма, ₽', { exact: true }).fill('100.40')
  await expect(remainder).toHaveText('Осталась не распределенная сумма 0,09 ₽')
  await expect(parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true })).toBeEnabled()
  await expect(parentDialog(page).locator('.deal-budget-error')).toHaveCount(0)
  await amount(page, 1).getByLabel('Сумма, ₽', { exact: true }).fill('100.49')
  await expect(remainder).toHaveCount(0)
  await amount(page, 1).getByLabel('Сумма, ₽', { exact: true }).fill('100.50')
  await expect(remainder).toHaveCount(0)
  await expect(parentDialog(page).locator('.deal-budget-error')).toContainText('до округления')
  await expect(parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled()
  await amount(page, 1).getByLabel('Сумма, ₽', { exact: true }).fill('')
  await expect(remainder).toHaveCount(0)
})

test('remainders use each expense independently and never subtract unlinked incomes', async ({ page }) => {
  await mountDeal(page)
  await page.evaluate(String.raw`(() => {
    const row = window.monetizationRow;
    const state = window.monetizationModalState;
    state.deal = {...state.deal,expenses:[row('a','10','leasing'),row('b','20','leasing'),row('c','30','leasing')],
      incomes:[row('linked-a','1.11','dealer','a'),row('linked-b','20','dealer','b'),row('legacy','100','dealer')]};
  })()`)
  await openAdjustment(page)
  const groups = parentDialog(page).locator('.calculation-group')
  await expect(groups.nth(0).locator('.deal-budget-remaining')).toHaveText('Осталась не распределенная сумма 8,89 ₽')
  await expect(groups.nth(1).locator('.deal-budget-remaining')).toHaveCount(0)
  await expect(groups.nth(2).locator('.deal-budget-remaining')).toHaveText('Осталась не распределенная сумма 30 ₽')
  await expect(groups.nth(3).locator('.deal-budget-remaining')).toHaveCount(0)
})

test('linked percentages retain exact before-rounding and cent-rounding budget checks', async ({ page }) => {
  await mountDeal(page)
  await page.evaluate(String.raw`(() => {
    const row = window.monetizationRow;
    const state = window.monetizationModalState;
    state.deal = {...state.deal,expenses:[row('expense','0.1','leasing')],
      incomes:[row('first','0.05','dealer','expense',{base_type:'expense_amount',calculation_base_amount:'0.1',percent:'50'}),
        row('second','0.04','dealer','expense',{base_type:'expense_amount',calculation_base_amount:'0.1',percent:'40'})]};
  })()`)
  await openAdjustment(page)
  await amount(page, 1).getByLabel('Процент', { exact: true }).fill('55')
  await amount(page, 2).getByLabel('Процент', { exact: true }).fill('45')
  await expect(parentDialog(page).locator('.deal-budget-error')).toHaveText('После округления сумма связанных доходов превышает расход.')
  await expect(parentDialog(page).locator('.deal-budget-remaining')).toHaveCount(0)
  await amount(page, 2).getByLabel('Процент', { exact: true }).fill('45.01')
  await expect(parentDialog(page).locator('.deal-budget-error')).toContainText('до округления')
  await amount(page, 2).getByLabel('Процент', { exact: true }).fill('44.99')
  await expect(parentDialog(page).locator('.deal-budget-error')).toHaveCount(0)
  await expect(parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true })).toBeEnabled()
})
test('persisted percent tracks its expense until direct amount input changes the calculation mode', async ({ page }) => {
  await mountDeal(page)
  await page.evaluate(String.raw`(() => {
    const state = window.monetizationModalState;
    state.deal = {...state.deal,incomes:[window.monetizationRow('income','20','dealer',state.deal.expenses[0].id,{
      percent:'20',original_percent:'20',input_mode:'percent',base_type:'expense_amount',calculation_base_amount:'100'
    })]};
  })()`)
  await openAdjustment(page)
  await amount(page, 0).getByLabel('Сумма, ₽', { exact: true }).fill('200')
  await expect(amount(page, 1).getByLabel('Процент', { exact: true })).toHaveValue('20')
  await expect(amount(page, 1).getByLabel('Сумма, ₽', { exact: true })).toHaveValue('40')
  await parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true }).click()
  await openAdjustment(page)
  await amount(page, 0).getByLabel('Сумма, ₽', { exact: true }).fill('300')
  await expect(amount(page, 1).getByLabel('Сумма, ₽', { exact: true })).toHaveValue('60')
  await amount(page, 1).getByLabel('Сумма, ₽', { exact: true }).fill('50')
  await expect(amount(page, 1).getByLabel('Процент', { exact: true })).toHaveValue('16.67')
  await amount(page, 0).getByLabel('Сумма, ₽', { exact: true }).fill('400')
  await expect(amount(page, 1).getByLabel('Сумма, ₽', { exact: true })).toHaveValue('50')
  await expect(amount(page, 1).getByLabel('Процент', { exact: true })).toHaveValue('12.5')
})

test('automatic income recalculation retains a historical precise rate without resubmitting it', async ({ page }) => {
  await mountDeal(page)
  await page.evaluate(String.raw`(() => {
    const state = window.monetizationModalState;
    state.deal = {...state.deal,incomes:[window.monetizationRow('historic-income','20','dealer',state.deal.expenses[0].id,{
      percent:'20.004',original_percent:'20.004',input_mode:'percent',base_type:'expense_amount',calculation_base_amount:'100'
    })]};
  })()`)
  await openAdjustment(page)
  await amount(page, 0).getByLabel('Сумма, ₽', { exact: true }).fill('200')
  await expect(amount(page, 1).getByLabel('Процент', { exact: true })).toHaveValue('20')
  await expect(amount(page, 1).getByLabel('Сумма, ₽', { exact: true })).toHaveValue('40.01')
  await parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true }).click()
  expect(await page.evaluate('window.monetizationModalState.calls[0].items')).toHaveLength(1)
  expect(await page.evaluate('window.monetizationModalState.deal.incomes[0].percent')).toBe('20.004')
  expect(await page.evaluate('window.monetizationModalState.deal.incomes[0].amount')).toBe('40.01')
})

test('new input rounding to zero is rejected while a positive amount may have zero equivalent percent', async ({ page }) => {
  await mountDeal(page)
  await openAdjustment(page)
  const money = amount(page).getByLabel('Сумма, ₽', { exact: true })
  await money.fill('0.004')
  await expect(amount(page).getByRole('alert')).toContainText('больше нуля')
  await expect(parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled()
  await money.fill('0.005')
  await expect(amount(page).getByLabel('Процент', { exact: true })).toHaveValue('0')
  await expect(amount(page).getByRole('alert')).toHaveCount(0)
  await expect(parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true })).toBeEnabled()
  await money.press('Enter')
  await expect(page.locator('#updated-amount')).toHaveText('0.01')
})
test('zero bases disable percent editing while fixed and clipped originals remain explained', async ({ page }) => {
  await mountDeal(page)
  await page.evaluate(String.raw`(() => {
    const row = window.monetizationRow;
    const state = window.monetizationModalState;
    state.deal = {...state.deal,expenses:[row('zero','0','leasing',null,{original_calc_type:'amount',original_percent:null,percent:'0'})],
      incomes:[row('income','0','dealer','zero',{base_type:'expense_amount',calculation_base_amount:'0',percent:null,original_percent:'20',clip:'max',raw_amount:'200'})]};
  })()`)
  await openAdjustment(page)
  await expect(amount(page, 0).locator('.deal-original-terms')).toContainText('Фиксированная сумма')
  await expect(amount(page, 1).locator('.clip-note')).toContainText('максимум')
  await expect(amount(page, 1).getByLabel('Процент', { exact: true })).toBeDisabled()
  await expect(amount(page, 1).getByLabel('Сумма, ₽', { exact: true })).toBeEnabled()
  await expect(parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled()
})

test('validation and revision conflicts preserve the draft without creating another dialog', async ({ page }) => {
  await mountDeal(page)
  await openAdjustment(page)
  await amount(page).getByLabel('Процент', { exact: true }).fill('10.123456789')
  await expect(amount(page).getByRole('alert')).toContainText('8 знаков')
  await expect(parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled()
  await amount(page).getByLabel('Процент', { exact: true }).fill('12')
  await page.evaluate('window.monetizationModalState.failure = 409')
  await parentDialog(page).getByRole('button', { name: 'Сохранить', exact: true }).click()
  await expect(parentDialog(page).getByRole('alert')).toContainText('Отмените черновик и обновите карточку')
  await expect(amount(page).getByLabel('Процент', { exact: true })).toHaveValue('12')
  await expect(page.getByRole('dialog')).toHaveCount(1)
  await parentDialog(page).getByRole('button', { name: 'Отмена', exact: true }).click()
  await expect(amount(page).locator('.deal-new-terms')).toHaveCount(0)
})

for (const width of [768, 1280, 1920]) {
  test('keeps expenses left, platform first and inline terms within the dialog at ' + width + 'px', async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1600 })
    await mountDeal(page)
    await page.evaluate(String.raw`(() => {
      const row = window.monetizationRow;
      const state = window.monetizationModalState;
      state.deal = {...state.deal,
        expenses:[row('expense-leasing','1000','leasing',null,{percent:'100'}),row('expense-platform','2000','platform',null,{percent:'200'})],
        incomes:[row('income-dealer-second','20','dealer','expense-platform',{percent:'2'}),row('income-dealer-first','10','dealer','expense-leasing',{percent:'1'}),row('income-platform','30','platform','expense-platform',{percent:'3'}),row('standalone-dealer','40','dealer',null,{percent:'4'}),row('standalone-platform','50','platform',null,{percent:'5'})],
      };
    })()`)
    await openAdjustment(page)
    const modal = parentDialog(page)
    const first = modal.getByRole('region', { name: 'Расход 1 и связанные доходы', exact: true })
    const second = modal.getByRole('region', { name: 'Расход 2 и связанные доходы', exact: true })
    await expect(first.locator('article')).toHaveCount(3)
    await expect(first.locator('article').nth(0)).toContainText('Платформа МЛ (Расход)')
    await expect(first.locator('article').nth(1)).toContainText('Платформа МЛ (Доход)')
    await expect(first.locator('article').nth(2)).toContainText('Дилер (Доход)')
    await expect(second).toContainText('1 000 ₽')
    const standalone = modal.getByRole('region', { name: 'Самостоятельные доходы', exact: true })
    await expect(standalone.locator('article').first()).toContainText('Платформа МЛ (Доход)')
    const expense = await first.locator('article').nth(0).boundingBox()
    const income = await first.locator('article').nth(1).boundingBox()
    expect(income!.x).toBeGreaterThanOrEqual(expense!.x + expense!.width)
    expect(Math.abs(income!.y - expense!.y)).toBeLessThanOrEqual(1)
    expect(await modal.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
    await modal.screenshot({ path: testInfo.outputPath('inline-terms-' + width + '.png') })
  })
}
