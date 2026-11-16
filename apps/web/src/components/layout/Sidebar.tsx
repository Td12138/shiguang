import { Link, NavLink } from 'react-router-dom';
import { NavIcon } from './NavIcon';
import { NAV_ITEMS } from './nav';
import styles from './Sidebar.module.css';

/** 桌面端左侧导航；<768px 由 BottomTabs 接管 */
export function Sidebar() {
  return (
    <aside className={styles.sidebar} aria-label="主导航">
      <Link to="/" className={styles.brand}>
        <img className={styles.logo} src="/logo.svg" alt="" width={40} height={40} />
        <span className={styles.brandText}>
          <strong className={styles.brandName}>食光</strong>
          <em className={styles.brandSub}>剩食管家</em>
        </span>
      </Link>

      <nav className={styles.nav}>
        <ul>
          {NAV_ITEMS.map((item) => (
            <li key={item.path}>
              <NavLink
                to={item.path}
                end={item.path === '/'}
                data-tour={item.tour}
                className={({ isActive }) =>
                  [styles.link, isActive ? styles.active : ''].filter(Boolean).join(' ')
                }
              >
                <NavIcon name={item.icon} />
                <span>{item.label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <p className={styles.note}>
        本地运行 · 支持 mock 回放
        <br />
        数据只存本机 SQLite
      </p>
    </aside>
  );
}
