import type { Calculation } from '~/features/checkout/store/checkout'
import type { CommerceLeasingCalculationPayload } from '~/features/commerce/types'

/**
 * Convert the interactive calculator response into the flat persistence
 * contract of leasing_application_calculations.
 */
export const buildApplicationCalculationPayload = (
  calculation: Calculation | null,
): CommerceLeasingCalculationPayload | undefined => {
  if (!calculation) return undefined
  return {
    total_amount: calculation.total_amount,
    down_payment: calculation.down_payment,
    down_payment_percent: calculation.down_payment_percent,
    lease_term_months: calculation.lease_term_months,
    monthly_payment: calculation.calculation?.monthlyPayment,
    total_cost: calculation.calculation?.totalCost,
    markup: calculation.calculation?.markup,
    rate: calculation.calculation?.rate,
    total_interest: calculation.calculation?.totalInterest,
    buyout_amount: calculation.buyout_amount ?? calculation.calculation?.buyoutAmount,
    vat_refund: calculation.calculation?.vatRefund,
    profit_tax_savings: calculation.calculation?.profitTaxSavings,
    total_savings: calculation.calculation?.totalSavings,
    selected_support: calculation.selected_support ?? {},
    support_per_vehicle: calculation.support_per_vehicle ?? [],
    support_per_program: calculation.support_per_program ?? [],
    support_program_details: calculation.support_program_details ?? [],
    calculations_per_vehicle: calculation.calculations_per_vehicle ?? [],
  }
}
