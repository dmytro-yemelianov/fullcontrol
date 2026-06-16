from pydantic import Field

from fullcontrol.core.base import BaseModelPlus


class ValidationResult(BaseModelPlus):
    '''Result of pre-flight validation: a list of issues, each {severity, message}
    where severity is 'error', 'warning' or 'info'.'''
    issues: list = Field(default_factory=list)

    def add(self, severity: str, message: str):
        self.issues.append({'severity': severity, 'message': message})

    @property
    def errors(self):
        return [i for i in self.issues if i['severity'] == 'error']

    @property
    def warnings(self):
        return [i for i in self.issues if i['severity'] == 'warning']

    @property
    def ok(self) -> bool:
        'True if there are no error-level issues.'
        return not self.errors

    def summary(self) -> str:
        if not self.issues:
            return 'validation passed: no issues found'
        return '\n'.join(f"[{i['severity']}] {i['message']}" for i in self.issues)

    def raise_if_errors(self):
        if not self.ok:
            raise ValueError('design validation failed:\n' + '\n'.join(e['message'] for e in self.errors))
