/**
 * Block-based formula model for computed metrics and KPI calculations.
 *
 * The dialog edits a FormulaGroup (a flat row of terms joined by operators,
 * with nested groups for parentheses). It serializes to the recursive AST
 * stored on the backend (see backend app/modules/semantic/formula.py) with
 * standard precedence: × and ÷ bind before + and −.
 */

// 'none' = the raw column value (no aggregation). A formula that uses any
// 'none' term is row-level and behaves like a raw measure.
export type FormulaAggName = 'sum' | 'avg' | 'min' | 'max' | 'count' | 'count_distinct' | 'none'
export type FormulaOp = '+' | '-' | '*' | '/'

export type FormulaNode =
  | { type: 'binary'; op: FormulaOp; left: FormulaNode; right: FormulaNode }
  | { type: 'agg'; agg: FormulaAggName; column: string }
  | { type: 'literal'; value: number }
  | { type: 'ref'; measure: string } // KPI mode only

export type FormulaTerm =
  | { kind: 'agg'; agg: FormulaAggName; column: string }
  | { kind: 'ref'; measure: string } // KPI mode only
  | { kind: 'literal'; value: number }
  | { kind: 'group'; group: FormulaGroup } // explicit parentheses

export interface FormulaGroup {
  terms: FormulaTerm[]
  ops: FormulaOp[] // ops.length === terms.length - 1
}

export const FORMULA_AGGS: FormulaAggName[] = ['sum', 'avg', 'min', 'max', 'count', 'count_distinct', 'none']
// Dropdown labels. "none" is the origin/raw value (no aggregation).
export const AGG_LABEL: Record<FormulaAggName, string> = {
  sum: 'SUM',
  avg: 'AVG',
  min: 'MIN',
  max: 'MAX',
  count: 'COUNT',
  count_distinct: 'COUNT DISTINCT',
  none: 'Raw value (no agg)',
}
export const OP_SYMBOL: Record<FormulaOp, string> = { '+': '+', '-': '−', '*': '×', '/': '÷' }

function termToAst(term: FormulaTerm): FormulaNode {
  if (term.kind === 'agg') return { type: 'agg', agg: term.agg, column: term.column }
  if (term.kind === 'ref') return { type: 'ref', measure: term.measure }
  if (term.kind === 'literal') return { type: 'literal', value: term.value }
  return groupToAst(term.group)
}

/** Serialize an edited group to the AST, folding × ÷ before + −. */
export function groupToAst(group: FormulaGroup): FormulaNode {
  const terms = group.terms.map(termToAst)
  if (!terms.length) throw new Error('Empty formula')

  // First pass: fold multiplicative runs left-to-right.
  const nodes: FormulaNode[] = [terms[0]]
  const addOps: FormulaOp[] = []
  for (let i = 0; i < group.ops.length; i++) {
    const op = group.ops[i]
    const term = terms[i + 1]
    if (op === '*' || op === '/') {
      nodes[nodes.length - 1] = { type: 'binary', op, left: nodes[nodes.length - 1], right: term }
    } else {
      nodes.push(term)
      addOps.push(op)
    }
  }
  // Second pass: fold additive runs left-to-right.
  let ast = nodes[0]
  for (let i = 0; i < addOps.length; i++) {
    ast = { type: 'binary', op: addOps[i], left: ast, right: nodes[i + 1] }
  }
  return ast
}

function leafOrGroup(node: FormulaNode): FormulaTerm {
  // A binary node in a leaf slot is always an explicit parenthesized group —
  // operator chains at the current level were already flattened by the caller.
  if (node.type === 'binary') return { kind: 'group', group: astToGroup(node) }
  if (node.type === 'agg') return { kind: 'agg', agg: node.agg, column: node.column }
  if (node.type === 'ref') return { kind: 'ref', measure: node.measure }
  return { kind: 'literal', value: node.value }
}

/** Inverse of groupToAst — flatten an AST back into editable rows. */
export function astToGroup(node: FormulaNode): FormulaGroup {
  const terms: FormulaTerm[] = []
  const ops: FormulaOp[] = []

  function pushMul(n: FormulaNode) {
    if (n.type === 'binary' && (n.op === '*' || n.op === '/')) {
      pushMul(n.left)
      ops.push(n.op)
      terms.push(leafOrGroup(n.right))
    } else {
      terms.push(leafOrGroup(n))
    }
  }

  function pushAdd(n: FormulaNode) {
    if (n.type === 'binary' && (n.op === '+' || n.op === '-')) {
      pushAdd(n.left)
      ops.push(n.op)
      pushMul(n.right)
    } else {
      pushMul(n)
    }
  }

  pushAdd(node)
  return { terms, ops }
}

/** Convert a legacy ratio expression for editing in the block builder. */
export function ratioToGroup(expression: Record<string, unknown>): FormulaGroup {
  const num = (expression.numerator ?? {}) as { agg?: string; column?: string }
  const den = (expression.denominator ?? {}) as { agg?: string; column?: string }
  const group: FormulaGroup = {
    terms: [
      { kind: 'agg', agg: (num.agg as FormulaAggName) || 'sum', column: num.column || '' },
      { kind: 'agg', agg: (den.agg as FormulaAggName) || 'sum', column: den.column || '' },
    ],
    ops: ['/'],
  }
  const multiplier = Number(expression.multiplier ?? 1)
  if (multiplier && multiplier !== 1) {
    group.terms.push({ kind: 'literal', value: multiplier })
    group.ops.push('*')
  }
  return group
}

/**
 * Evaluate a ref/literal/binary formula over already-aggregated values
 * (KPI custom calculations). Division by zero and missing refs yield null.
 */
export function evaluateFormula(
  node: FormulaNode,
  refs: Record<string, number | null | undefined>,
): number | null {
  if (node.type === 'binary') {
    const left = evaluateFormula(node.left, refs)
    const right = evaluateFormula(node.right, refs)
    if (left == null || right == null) return null
    if (node.op === '+') return left + right
    if (node.op === '-') return left - right
    if (node.op === '*') return left * right
    return right === 0 ? null : left / right
  }
  if (node.type === 'literal') return node.value
  if (node.type === 'ref') {
    const value = refs[node.measure]
    return value == null ? null : Number(value)
  }
  return null // agg nodes are not evaluable over query results
}

/** Human-readable rendering of a group, e.g. (SUM(Revenue) − SUM(Spend)) ÷ SUM(Spend) × 100 */
export function formatGroup(group: FormulaGroup, labelFor: (name: string) => string): string {
  const parts: string[] = []
  group.terms.forEach((term, i) => {
    if (i > 0) parts.push(OP_SYMBOL[group.ops[i - 1]])
    if (term.kind === 'agg') {
      parts.push(term.agg === 'none' ? labelFor(term.column) : `${term.agg.toUpperCase()}(${labelFor(term.column)})`)
    } else if (term.kind === 'ref') parts.push(labelFor(term.measure))
    else if (term.kind === 'literal') parts.push(String(term.value))
    else parts.push(`( ${formatGroup(term.group, labelFor)} )`)
  })
  return parts.join(' ')
}

/** True when every term is filled in and the group is non-empty. */
export function isGroupComplete(group: FormulaGroup): boolean {
  if (!group.terms.length) return false
  return group.terms.every((term) => {
    if (term.kind === 'agg') return !!term.column
    if (term.kind === 'ref') return !!term.measure
    if (term.kind === 'literal') return Number.isFinite(term.value)
    return isGroupComplete(term.group)
  })
}
