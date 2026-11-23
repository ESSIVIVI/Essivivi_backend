"""Déclencheur : toute modification du mode, du salaire ou du taux de commission
d'un agent est consignée dans agent_pay_history (historique consultable par l'admin).

L'auteur est lu dans le réglage de session app.user_id ; l'API doit exécuter,
dans la même transaction et avant la mise à jour :
    SET LOCAL app.user_id = '<id de l'administrateur>';
"""
from django.db import migrations

CREATE = """
CREATE FUNCTION log_agent_pay_change() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO agent_pay_history (agent_id, new_pay_mode, new_monthly_salary, new_commission_rate, changed_by_id, changed_at)
        VALUES (NEW.user_id, NEW.pay_mode, NEW.monthly_salary, NEW.commission_rate,
                NULLIF(current_setting('app.user_id', true), '')::bigint, now());
    ELSIF (NEW.pay_mode, NEW.monthly_salary, NEW.commission_rate)
          IS DISTINCT FROM (OLD.pay_mode, OLD.monthly_salary, OLD.commission_rate) THEN
        INSERT INTO agent_pay_history (agent_id, old_pay_mode, old_monthly_salary, old_commission_rate,
                                       new_pay_mode, new_monthly_salary, new_commission_rate, changed_by_id, changed_at)
        VALUES (NEW.user_id, OLD.pay_mode, OLD.monthly_salary, OLD.commission_rate,
                NEW.pay_mode, NEW.monthly_salary, NEW.commission_rate,
                NULLIF(current_setting('app.user_id', true), '')::bigint, now());
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agent_pay_history_trg
    AFTER INSERT OR UPDATE ON agent
    FOR EACH ROW EXECUTE FUNCTION log_agent_pay_change();
"""

DROP = """
DROP TRIGGER IF EXISTS agent_pay_history_trg ON agent;
DROP FUNCTION IF EXISTS log_agent_pay_change();
"""


class Migration(migrations.Migration):
    dependencies = [("agents", "0001_initial")]
    operations = [migrations.RunSQL(CREATE, DROP)]
