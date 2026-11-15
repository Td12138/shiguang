import { NavLink } from 'react-router-dom';
import { NavIcon } from './NavIcon';
import { NAV_ITEMS } from './nav';
import styles from './BottomTabs.module.css';

/** 移动端底部 Tab（<768px）：与侧栏同一份 NAV_ITEMS，避免两处维护 */
export function BottomTabs() {
  return (
    <nav className={styles.tabbar} aria-label="底部主导航">
      <ul className={styles.list}>
        {NAV_ITEMS.map((item) => (
          <li key={item.path} className={styles.item}>
            <NavLink
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) =>
                [styles.tab, isActive ? styles.active : ''].filter(Boolean).join(' ')
              }
            >
              <NavIcon name={item.icon} />
              <span className={styles.label}>{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
