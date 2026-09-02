import { Icon } from "./Icon";

const GITHUB_USER = "https://github.com/Candacewade";
const GITHUB_REPO = "https://github.com/Candacewade/can-i-park-here-chicago";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <p className="foot-transparency">
        A deterministic rule engine decides legality and move-by times from City of Chicago
        data. An AI agent only investigates context — weather, events, nearby alternatives
        — and writes the explanation; it never changes the verdict.
      </p>
      <p className="foot-data">
        <Icon name="shield" size={14} /> Data: City of Chicago Open Data Portal, US Census
        Bureau geocoder &amp; the US National Weather Service. Not affiliated with the City
        of Chicago.
      </p>
      <div className="foot-about">
        <a className="foot-gh" href={GITHUB_USER} target="_blank" rel="noreferrer">
          <Icon name="github" size={16} /> Candacewade
        </a>
        <span>
          Built by Candace Wade — a software engineer using hands-on projects to go deep on
          AI agents, the Model Context Protocol, and safe, deterministic decision systems.
        </span>
        <a href={GITHUB_REPO} target="_blank" rel="noreferrer">
          Source on GitHub →
        </a>
      </div>
    </footer>
  );
}
