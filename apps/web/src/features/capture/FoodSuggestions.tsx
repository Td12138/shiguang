import { FOOD_LIST_ID, FOOD_NAMES } from '@/lib/foods';

/** 69 种食材的补全源：原生 datalist，移动端键盘与系统建议都能用，零依赖 */
export function FoodSuggestions() {
  return (
    <datalist id={FOOD_LIST_ID}>
      {FOOD_NAMES.map((name) => (
        <option key={name} value={name} />
      ))}
    </datalist>
  );
}
