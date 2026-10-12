"""
Formularios de la app de diagnóstico.

RegistroUsuarioForm: alta de usuarios desde la web (reemplaza al
createsuperuser por terminal como única vía). Extiende UserCreationForm
para heredar la validación de contraseñas de Django (settings
AUTH_PASSWORD_VALIDATORS) y traduce las etiquetas al español.
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegistroUsuarioForm(UserCreationForm):
    """Registro público: usuario, correo (opcional) y contraseña doble."""

    email = forms.EmailField(
        required=False,
        label="Correo electrónico (opcional)",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Etiquetas y ayudas en español (UserCreationForm las trae en inglés)
        self.fields["username"].label = "Usuario"
        self.fields["username"].help_text = "Hasta 150 caracteres: letras, dígitos y @/./+/-/_"
        self.fields["password1"].label = "Contraseña"
        self.fields["password2"].label = "Confirmar contraseña"
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "campo-input")

    def clean_email(self):
        """Evita correos duplicados solo si el usuario ingresó uno."""
        email = self.cleaned_data.get("email", "").strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo.")
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.email = self.cleaned_data.get("email", "")
        if commit:
            usuario.save()
        return usuario
