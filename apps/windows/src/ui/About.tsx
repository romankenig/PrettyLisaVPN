import { useState } from "react";
import { SupportDialog } from "./SupportDialog";

export function About({
  frontend,
  backend,
}: {
  readonly frontend: string;
  readonly backend: string;
}) {
  const [supportOpen, setSupportOpen] = useState(false);
  return (
    <section className="about-page" aria-labelledby="about-title">
      <h1 id="about-title">о приложении</h1>
      <dl className="about-versions" aria-label="версии компонентов">
        <div>
          <dt>frontend</dt>
          <dd>{frontend}</dd>
        </div>
        <div>
          <dt>backend</dt>
          <dd>{backend}</dd>
        </div>
      </dl>
      <div className="about-sections">
        <section className="about-card" aria-labelledby="faq-title">
          <h2 id="faq-title">faq</h2>
        </section>
        <section className="about-card" aria-labelledby="support-title">
          <h2 id="support-title">помощь и поддержка</h2>
          <p>расскажите, с чем нужна помощь</p>
          <button type="button" onClick={() => setSupportOpen(true)}>
            написать в поддержку
          </button>
        </section>
      </div>
      <p className="about-dedication">inspired by love of my life, Lisa</p>
      {supportOpen ? (
        <SupportDialog
          frontend={frontend}
          backend={backend}
          onClose={() => setSupportOpen(false)}
        />
      ) : null}
    </section>
  );
}
