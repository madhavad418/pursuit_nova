const ADMIN_NAMES_HIDDEN_FROM_PICKERS = ['santosh', 'satish']

const text = value => String(value || '').toLowerCase()

// "Santosh Admin" / "Satish Admin" style accounts: first name matches AND the account is an admin (by role or by name)
export function isRequestedHiddenAdmin(user) {
  const name = text(user?.name)
  const role = text(user?.role)
  return ADMIN_NAMES_HIDDEN_FROM_PICKERS.some(n => name.includes(n) && (role.includes('admin') || name.includes('admin')))
}

export function visiblePickerUsers(users = [], { hideKamalakar = false, hideSuperAdmin = false } = {}) {
  return users.filter(u => {
    const combined = `${text(u?.name)} ${text(u?.role)}`
    if (isRequestedHiddenAdmin(u)) return false
    if (hideKamalakar && /kamalakar|kamlakar/i.test(u?.name || '')) return false
    if (hideSuperAdmin && /super admin/i.test(combined)) return false
    return true
  })
}
