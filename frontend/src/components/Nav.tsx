import { Icon } from "./Icon";

const GITHUB = "https://github.com/Candacewade/can-i-park-here-chicago";

export function Nav() {
  return (
    <nav className="nav">
      <a className="brand" href="/" aria-label="Can I Park Here home">
        <span className="brand-mark" aria-hidden="true">
          P
        </span>
        <span className="brand-name">Can I Park Here, Chicago?</span>
      </a>
      <div className="nav-right">
        <span className="nav-city">
          <Icon name="pin" size={15} /> Chicago, IL
        </span>
        <a className="nav-gh" href={GITHUB} target="_blank" rel="noreferrer" aria-label="View source on GitHub">
          <Icon name="github" size={18} />
        </a>
      </div>
    </nav>
  );
}
