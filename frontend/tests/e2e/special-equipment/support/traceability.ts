import type { TestInfo } from '@playwright/test'
import * as ts from 'typescript'

export const REQUIRED_ACCEPTANCE_CRITERIA = {
  '21940': Array.from({ length: 19 }, (_, index) => `AC-${index + 1}`),
  '21954': Array.from({ length: 25 }, (_, index) => `AC-${index + 1}`),
  '21984': Array.from({ length: 18 }, (_, index) => `AC-${index + 1}`),
  '22098': Array.from({ length: 6 }, (_, index) => `AC-${index + 1}`),
} as const

export const ALLOWED_REQUIREMENTS = {
  '21940': [
    ...Array.from({ length: 33 }, (_, index) => `FR-${index + 1}`),
    ...Array.from({ length: 7 }, (_, index) => `NFR-${index + 1}`),
  ],
  '21954': [
    ...Array.from({ length: 73 }, (_, index) => `FR-${index + 1}`),
    ...Array.from({ length: 12 }, (_, index) => `NFR-${index + 1}`),
  ],
  '21984': [
    ...Array.from({ length: 17 }, (_, index) => `FR-${index + 1}`),
    ...Array.from({ length: 3 }, (_, index) => `NFR-${index + 1}`),
  ],
  '22098': [
    ...Array.from({ length: 6 }, (_, index) => `FR-${index + 1}`),
    ...Array.from({ length: 3 }, (_, index) => `NFR-${index + 1}`),
  ],
} as const

export type BitrixTaskId = keyof typeof REQUIRED_ACCEPTANCE_CRITERIA
export type E2ETestKind = 'full-stack' | 'fault-injection' | 'contract-guard'

export interface Traceability {
  task: BitrixTaskId
  ac: string | readonly string[]
  fr?: string | readonly string[]
  kind: E2ETestKind
}

const asArray = (value: string | readonly string[] | undefined): readonly string[] =>
  value === undefined ? [] : typeof value === 'string' ? [value] : value

export const annotateTraceability = (testInfo: TestInfo, coverage: Traceability): void => {
  testInfo.annotations.push({ type: 'task', description: coverage.task })
  for (const ac of asArray(coverage.ac)) testInfo.annotations.push({ type: 'AC', description: ac })
  for (const fr of asArray(coverage.fr)) testInfo.annotations.push({ type: 'FR', description: fr })
  testInfo.annotations.push({ type: 'kind', description: coverage.kind })
}

export interface SourceTraceabilityMapping {
  task: BitrixTaskId
  ac: readonly string[]
  fr: readonly string[]
  kind: E2ETestKind
}

const property = (object: ts.ObjectLiteralExpression, name: string): ts.Expression | undefined => {
  const assignment = object.properties.find((candidate): candidate is ts.PropertyAssignment =>
    ts.isPropertyAssignment(candidate)
    && ((ts.isIdentifier(candidate.name) || ts.isStringLiteral(candidate.name)) && candidate.name.text === name),
  )
  return assignment?.initializer
}

const stringLiteral = (expression: ts.Expression | undefined): string | undefined =>
  expression && ts.isStringLiteralLike(expression) ? expression.text : undefined

const stringLiteralList = (expression: ts.Expression | undefined): string[] => {
  if (!expression) return []
  if (ts.isStringLiteralLike(expression)) return [expression.text]
  if (!ts.isArrayLiteralExpression(expression)) return []
  return expression.elements
    .filter((element): element is ts.StringLiteralLike => ts.isStringLiteralLike(element))
    .map(element => element.text)
}

const isPlaywrightTestCall = (node: ts.CallExpression): boolean =>
  ts.isIdentifier(node.expression) && node.expression.text === 'test'

const enclosingExecutableTest = (node: ts.Node): ts.FunctionLikeDeclaration | undefined => {
  let current: ts.Node | undefined = node
  while (current?.parent) {
    if (
      (ts.isArrowFunction(current) || ts.isFunctionExpression(current))
      && ts.isCallExpression(current.parent)
      && isPlaywrightTestCall(current.parent)
      && current.parent.arguments.includes(current)
    ) return current
    current = current.parent
  }
  return undefined
}

const hasAssertion = (testCallback: ts.FunctionLikeDeclaration): boolean => {
  let found = false
  const visit = (node: ts.Node): void => {
    if (
      ts.isCallExpression(node)
      && ts.isIdentifier(node.expression)
      && node.expression.text === 'expect'
    ) found = true
    if (!found) ts.forEachChild(node, visit)
  }
  visit(testCallback)
  return found
}

/**
 * Reads only literal annotateTraceability(testInfo, {...}) calls inside an
 * actual Playwright test callback that contains an assertion. AC tokens in a
 * title/comment and annotation-only tests cannot satisfy executable coverage.
 */
export const traceabilityMappingsInSource = (source: string): SourceTraceabilityMapping[] => {
  const mappings: SourceTraceabilityMapping[] = []
  const sourceFile = ts.createSourceFile('traceability-source.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const visit = (node: ts.Node): void => {
    if (
      ts.isCallExpression(node)
      && ts.isIdentifier(node.expression)
      && node.expression.text === 'annotateTraceability'
      && node.arguments.length >= 2
      && ts.isObjectLiteralExpression(node.arguments[1])
    ) {
      const testCallback = enclosingExecutableTest(node)
      if (!testCallback || !hasAssertion(testCallback)) {
        ts.forEachChild(node, visit)
        return
      }
      const object = node.arguments[1]
      const task = stringLiteral(property(object, 'task'))
      const kind = stringLiteral(property(object, 'kind'))
      const ac = stringLiteralList(property(object, 'ac'))
      const fr = stringLiteralList(property(object, 'fr'))
      if (
        task && task in REQUIRED_ACCEPTANCE_CRITERIA
        && kind && ['full-stack', 'fault-injection', 'contract-guard'].includes(kind)
        && ac.length > 0
      ) {
        mappings.push({ task: task as BitrixTaskId, ac, fr, kind: kind as E2ETestKind })
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sourceFile)
  return mappings
}

export const acceptanceCriteriaInSource = (task: BitrixTaskId, source: string): Set<string> =>
  new Set(
    traceabilityMappingsInSource(source)
      .filter(mapping => mapping.task === task)
      .flatMap(mapping => mapping.ac),
  )

export const missingAcceptanceCriteria = (task: BitrixTaskId, sources: readonly string[]): string[] => {
  const actual = acceptanceCriteriaInSource(task, sources.join('\n'))
  return REQUIRED_ACCEPTANCE_CRITERIA[task].filter(ac => !actual.has(ac))
}

export const unexpectedAcceptanceCriteria = (task: BitrixTaskId, sources: readonly string[]): string[] => {
  const required = new Set<string>(REQUIRED_ACCEPTANCE_CRITERIA[task])
  return [...acceptanceCriteriaInSource(task, sources.join('\n'))]
    .filter(ac => !required.has(ac))
    .sort()
}

export const unexpectedRequirements = (task: BitrixTaskId, sources: readonly string[]): string[] => {
  const allowed = new Set<string>(ALLOWED_REQUIREMENTS[task])
  return [...new Set(
    sources
      .flatMap(traceabilityMappingsInSource)
      .filter(mapping => mapping.task === task)
      .flatMap(mapping => mapping.fr),
  )].filter(requirement => !allowed.has(requirement)).sort()
}
