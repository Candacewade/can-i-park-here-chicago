import { Icon } from "./Icon";

const LINKEDIN = "https://www.linkedin.com/in/candace-k-wade/";
const GITHUB_REPO = "https://github.com/Candacewade/can-i-park-here-chicago";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <p className="foot-data">
        <Icon name="shield" size={14} /> Data: City of Chicago Open Data Portal, US Census
        Bureau geocoder &amp; the US National Weather Service. Not affiliated with the City
        of Chicago.
      </p>
      <div className="foot-about">
        <span>
          Built by{" "}
          <a href={LINKEDIN} target="_blank" rel="noreferrer">
            Candace Wade
          </a>
          , a software engineer and current computer science master's student at the
          University of Chicago. Candace enjoys using hands-on projects to go deep on
          full-stack development and AI while solving real-world problems (like not getting
          more of those orange-envelope parking tickets anymore, please 🤞).
        </span>
        <a className="foot-gh" href={GITHUB_REPO} target="_blank" rel="noreferrer">
          <Icon name="github" size={16} /> Source on GitHub →
        </a>
      </div>
    </footer>
  );
}
