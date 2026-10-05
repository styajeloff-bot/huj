import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import {
  annotateTraceability,
  missingAcceptanceCriteria,
  REQUIRED_ACCEPTANCE_CRITERIA,
  traceabilityMappingsInSource,
  type BitrixTaskId,
  unexpectedAcceptanceCriteria,
  unexpectedRequirements,
} from './support/traceability'

const suiteDirectory = __dirname

const taskSources = (task: BitrixTaskId): string[] => readdirSync(suiteDirectory)
  .filter(name => name.includes(task) && name.endsWith('.spec.ts') && name !== 'traceability.guard.spec.ts')
  .map(name => readFileSync(join(suiteDirectory, name), 'utf8'))

for (const task of Object.keys(REQUIRED_ACCEPTANCE_CRITERIA) as BitrixTaskId[]) {
  test(`Bitrix ${task}: every mandatory AC has an executable mapping`, async ({}, testInfo) => {
    annotateTraceability(testInfo, { task, ac: REQUIRED_ACCEPTANCE_CRITERIA[task], kind: 'contract-guard' })
    const sources = taskSources(task)
    test.skip(sources.length === 0, `E2E suite for Bitrix ${task} is owned by another parallel implementation slice`)
    expect(sources.flatMap(traceabilityMappingsInSource).length).toBeGreaterThan(0)
    expect(missingAcceptanceCriteria(task, sources)).toEqual([])
    expect(unexpectedAcceptanceCriteria(task, sources)).toEqual([])
    expect(unexpectedRequirements(task, sources)).toEqual([])
  })
}

test('only asserted Playwright tests with valid requirement identifiers satisfy traceability', () => {
  const source = `
    // AC-1 AC-2
    test('AC-3 is only a title', () => {})
    // annotateTraceability(testInfo, { task: '21954', ac: 'AC-5', kind: 'full-stack' })
    const fake = "annotateTraceability(testInfo, { task: '21954', ac: 'AC-6', kind: 'full-stack' })"
    annotateTraceability(testInfo, { task: '21954', ac: 'AC-4', kind: 'full-stack' })
    test('annotation without an assertion is not executable coverage', async ({}, testInfo) => {
      annotateTraceability(testInfo, { task: '21954', ac: 'AC-7', kind: 'full-stack' })
    })
    test('asserted mapping', async ({}, testInfo) => {
      annotateTraceability(testInfo, { task: '21954', ac: 'AC-4', fr: ['FR-1', 'NFR-99'], kind: 'full-stack' })
      expect(true).toBe(true)
    })
  `
  expect(missingAcceptanceCriteria('21954', [source]).slice(0, 6)).toEqual(['AC-1', 'AC-2', 'AC-3', 'AC-5', 'AC-6', 'AC-7'])
  expect(unexpectedRequirements('21954', [source])).toEqual(['NFR-99'])
})
