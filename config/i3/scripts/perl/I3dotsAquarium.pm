package I3dotsAquarium;
# Loaded by Aquarium.sh (perl -MI3dotsAquarium): asciiquarium paints every empty cell black, so a see-through
# terminal shows a black box. This makes it use the terminal's own background instead (curses "default colours"),
# which the terminal draws see-through like everywhere else - the wallpaper shows behind the fish.
# Nothing is changed on the system: it only adjusts Term::Animation (asciiquarium's library) while it runs.
use strict;
use warnings;
use Curses ();
use Term::Animation ();

{
    no strict 'refs';
    no warnings 'redefine';
    # Term::Animation picks the background with eval "Curses::COLOR_$self->{BG}": this one means "the default"
    *{"Curses::COLOR_I3DOTSDEFAULT"} = sub () { -1 };
    if (defined &Term::Animation::_set_colors) {
        my $orig = \&Term::Animation::_set_colors;
        *Term::Animation::_set_colors = sub {
            my $self = shift;
            if (!defined $self->{BG} || $self->{BG} eq 'BLACK') {
                # (only when the terminal supports it - otherwise asciiquarium stays as it was)
                if (eval { Curses::use_default_colors() != Curses::ERR() }) {
                    $self->{BG} = 'I3DOTSDEFAULT';
                }
            }
            return $orig->($self, @_);
        };
    }
}

1;
